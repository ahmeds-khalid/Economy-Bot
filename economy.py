import nextcord
from nextcord import Interaction, SlashOption, ui
from nextcord.ext import commands
from datetime import datetime, timedelta, timezone
import random
from config import BotConfig

class ConfirmationModal(ui.Modal):
    def __init__(self, correct_code: str, target_user: nextcord.Member, amount: int):
        super().__init__(title="Admin Verification Required")
        self.correct_code = correct_code
        self.target_user = target_user
        self.amount = amount

        self.confirmation_code = ui.TextInput(
            label="Enter Admin Confirmation Code",
            placeholder="Enter the code here...",
            min_length=1,
            max_length=20,
            required=True
        )
        self.add_item(self.confirmation_code)

    async def callback(self, interaction: Interaction):
        if self.confirmation_code.value == self.correct_code:
            try:
                economy_cog = interaction.client.get_cog("Economy")
                with economy_cog.bot.db.conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_balance (user_id, guild_id, balance)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, guild_id) 
                        DO UPDATE SET balance = %s
                    """, (self.target_user.id, interaction.guild.id, self.amount, self.amount))
                    economy_cog.bot.db.conn.commit()
                
                embed = nextcord.Embed(
                    title="Balance Modified",
                    description=f"Successfully set {self.target_user.mention}'s balance to {self.amount:,} coins",
                    color=nextcord.Color.green()
                )
                embed.set_footer(
                    text=f"Modified by {interaction.user}",
                    icon_url=interaction.user.display_avatar.url
                )
                await interaction.response.send_message(embed=embed)
                
            except Exception as e:
                await interaction.response.send_message(
                    f"Error setting balance: {str(e)}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Invalid confirmation code. Action cancelled.",
                ephemeral=True
            )

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = BotConfig()
        self.admin_code = self.config.ADMIN_CODE
    
    def calculate_message_reward(self, message_length: int) -> int:
        try:
            formula = self.config.MESSAGE_REWARD_FORMULA.replace("%length%", str(message_length))
            return int(eval(formula))
        except Exception as e:
            print(f"Error calculating message reward: {str(e)}")
            return 0

    def add_money(self, user_id: int, guild_id: int, amount: int):
        with self.bot.db.conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO user_balance (user_id, guild_id, balance)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, guild_id) 
                    DO UPDATE SET balance = user_balance.balance + %s
                """, (user_id, guild_id, amount, amount))
                self.bot.db.conn.commit()
            except Exception as e:
                self.bot.db.conn.rollback()
                raise

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
            
        try:
            reward = self.calculate_message_reward(len(message.content))
            if reward > 0:
                self.add_money(
                    user_id=message.author.id,
                    guild_id=message.guild.id,
                    amount=reward
                )
        except Exception as e:
            print(f"Error processing message reward: {str(e)}")

    def get_balance(self, user_id: int, guild_id: int) -> int:
        with self.bot.db.conn.cursor() as cur:
            cur.execute("""
                SELECT balance FROM user_balance 
                WHERE user_id = %s AND guild_id = %s
            """, (user_id, guild_id))
            result = cur.fetchone()
            return result[0] if result else self.config.INITIAL_BALANCE

    @nextcord.slash_command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: Interaction):
        try:
            success, amount = self.claim_daily(interaction.user.id, interaction.guild.id)
            if success:
                await interaction.response.send_message(
                    f"You received {amount} coins as your daily reward!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "You've already claimed your daily reward. Try again in 24 hours!",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"Error claiming daily reward: {str(e)}",
                ephemeral=True
            )

    def claim_daily(self, user_id: int, guild_id: int) -> tuple[bool, int]:
        with self.bot.db.conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT last_daily FROM user_balance 
                    WHERE user_id = %s AND guild_id = %s
                    FOR UPDATE
                """, (user_id, guild_id))
                
                result = cur.fetchone()
                now = datetime.now(timezone.utc)
                
                if result and result[0]:
                    time_diff = now - result[0]
                    if time_diff < timedelta(hours=24):
                        return False, 0

                amount = random.randint(
                    self.config.DAILY_MIN_AMOUNT,
                    self.config.DAILY_MAX_AMOUNT
                )
                
                cur.execute("""
                    INSERT INTO user_balance (user_id, guild_id, balance, last_daily)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, guild_id) 
                    DO UPDATE SET 
                        balance = user_balance.balance + %s,
                        last_daily = %s
                """, (user_id, guild_id, amount, now, amount, now))
                
                self.bot.db.conn.commit()
                return True, amount
                
            except Exception as e:
                self.bot.db.conn.rollback()
                raise

    @nextcord.slash_command(name="balance", description="Check balance")
    async def balance(
        self,
        interaction: Interaction,
        user: nextcord.Member = SlashOption(
            description="User to check (leave empty for self)",
            required=False
        )
    ):
        target_user = user or interaction.user
        
        # Changed from administrator to manage_guild
        if user and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You don't have permission to check other users' balance!",
                ephemeral=True
            )
            return

        try:
            balance = self.get_balance(target_user.id, interaction.guild.id)
            
            embed = nextcord.Embed(
                title=f"Balance for {target_user.display_name}",
                color=nextcord.Color.green()
            )
            embed.add_field(name="Current Balance", value=f"{balance:,} coins")
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"Error checking balance: {str(e)}",
                ephemeral=True
            )


    @nextcord.slash_command(name="set", description="Set a user's balance")
    async def set_balance(
        self,
        interaction: Interaction,
        user: nextcord.Member = SlashOption(description="User to modify balance"),
        amount: int = SlashOption(description="New balance amount", min_value=0)
    ):
        # Show modal for confirmation code
        modal = ConfirmationModal(self.admin_code, user, amount)
        await interaction.response.send_modal(modal)

    @nextcord.slash_command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: Interaction):
        try:
            success, amount = self.claim_daily(interaction.user.id, interaction.guild.id)
            if success:
                await interaction.response.send_message(
                    f"You received {amount} coins as your daily reward!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "You've already claimed your daily reward. Try again in 24 hours!",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"Error claiming daily reward: {str(e)}",
                ephemeral=True
            )

    @nextcord.slash_command(name="balance", description="Check balance")
    async def balance(
        self,
        interaction: Interaction,
        user: nextcord.Member = SlashOption(
            description="User to check (leave empty for self)",
            required=False
        )
    ):
        target_user = user or interaction.user
        
        if user and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You don't have permission to check other users' balance!",
                ephemeral=True
            )
            return

        try:
            balance = self.get_balance(target_user.id, interaction.guild.id)
            
            embed = nextcord.Embed(
                title=f"Balance for {target_user.display_name}",
                color=nextcord.Color.green()
            )
            embed.add_field(name="Current Balance", value=f"{balance:,} coins")
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"Error checking balance: {str(e)}",
                ephemeral=True
            )

    def transfer_money(self, from_user: int, to_user: int, guild_id: int, amount: int) -> bool:
        with self.bot.db.conn.cursor() as cur:
            try:
                cur.execute("BEGIN")
                
                # Check sender's balance
                cur.execute("""
                    SELECT balance FROM user_balance 
                    WHERE user_id = %s AND guild_id = %s
                    FOR UPDATE
                """, (from_user, guild_id))
                
                sender_balance = cur.fetchone()
                if not sender_balance or sender_balance[0] < amount:
                    cur.execute("ROLLBACK")
                    return False

                # Update sender's balance
                cur.execute("""
                    UPDATE user_balance 
                    SET balance = balance - %s 
                    WHERE user_id = %s AND guild_id = %s
                """, (amount, from_user, guild_id))

                # Update receiver's balance
                cur.execute("""
                    INSERT INTO user_balance (user_id, guild_id, balance)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, guild_id) 
                    DO UPDATE SET balance = user_balance.balance + %s
                """, (to_user, guild_id, amount, amount))

                cur.execute("COMMIT")
                return True
                
            except Exception as e:
                cur.execute("ROLLBACK")
                raise

    @nextcord.slash_command(name="pay", description="Pay another user")
    async def pay(
        self,
        interaction: Interaction,
        user: nextcord.Member = SlashOption(description="User to pay"),
        amount: int = SlashOption(description="Amount to pay", min_value=1)
    ):
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You can't pay yourself!",
                ephemeral=True
            )
            return

        try:
            success = self.transfer_money(
                interaction.user.id,
                user.id,
                interaction.guild.id,
                amount
            )
            
            if success:
                await interaction.response.send_message(
                    f"Successfully sent {amount:,} coins to {user.mention}!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You don't have enough coins!",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"Error processing payment: {str(e)}",
                ephemeral=True
            )

    def get_leaderboard(self, guild_id: int, limit: int = 10) -> list:
        with self.bot.db.conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, balance
                FROM user_balance
                WHERE guild_id = %s
                ORDER BY balance DESC
                LIMIT %s
            """, (guild_id, limit))
            
            return cur.fetchall()

    @nextcord.slash_command(name="leaderboard", description="Show top 10 richest users")
    async def leaderboard(self, interaction: Interaction):
        try:
            leaders = self.get_leaderboard(interaction.guild.id)
            
            if not leaders:
                await interaction.response.send_message(
                    "No users found in the leaderboard!",
                    ephemeral=True
                )
                return

            embed = nextcord.Embed(
                title="🏆 Economy Leaderboard",
                description="**Top 10 Richest Users**",
                color=nextcord.Color.gold()
            )

            medals = ["🥇", "🥈", "🥉"]
            for i, leader in enumerate(leaders, 1):
                user = interaction.guild.get_member(leader[0])  # user_id is first column
                if user:
                    medal = medals[i-1] if i <= 3 else f"#{i}"
                    embed.add_field(
                        name=f"{medal} {user.display_name}",
                        value=f"**{leader[1]:,}** coins",  # balance is second column
                        inline=False
                    )

            embed.set_footer(
                text=f"Requested by {interaction.user}",
                icon_url=interaction.user.display_avatar.url
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(
                f"Error retrieving leaderboard: {str(e)}",
                ephemeral=True
            )

def setup(bot):
    bot.add_cog(Economy(bot))