import nextcord
from nextcord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

POSTGRES_URI = os.getenv('POSTGRES_URI')
BOT_TOKEN = os.getenv('BOT_TOKEN')
SCHEMA_NAME = 'economy_schema'

class Database:
    def __init__(self):
        try:
            self.conn = psycopg2.connect(POSTGRES_URI)
            self.conn.autocommit = True
            
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT schema_name 
                    FROM information_schema.schemata 
                    WHERE schema_name = %s;
                """, (SCHEMA_NAME,))
                
                if not cur.fetchone():
                    print(f"Creating schema {SCHEMA_NAME}...")
                    cur.execute(f"CREATE SCHEMA {SCHEMA_NAME};")
                    print(f"Schema {SCHEMA_NAME} created successfully!")
                
                cur.execute(f"SET search_path TO {SCHEMA_NAME};")
            
            self.conn.autocommit = False
            
        except Exception as e:
            print(f"Error in database initialization: {str(e)}")
            raise
        
    def setup_database(self):
        with self.conn.cursor() as cur:
            try:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_balance (
                        user_id BIGINT NOT NULL,
                        guild_id BIGINT NOT NULL,
                        balance BIGINT DEFAULT 100,
                        last_daily TIMESTAMP WITH TIME ZONE,
                        PRIMARY KEY (user_id, guild_id)
                    );
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_balance_user_id ON user_balance(user_id);
                    CREATE INDEX IF NOT EXISTS idx_balance_guild_id ON user_balance(guild_id);
                """)
                
                self.conn.commit()
                print("Tables and indexes created successfully!")
                
            except Exception as e:
                self.conn.rollback()
                print(f"Error creating tables: {str(e)}")
                raise

class EconomyBot(commands.Bot):
    def __init__(self):
        intents = nextcord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        
        # Initialize database connection
        self.db = Database()
        
    async def on_ready(self):
        print(f'Bot is ready! Logged in as {self.user.name}')
        try:
            self.db.setup_database()
            print("Database setup completed successfully!")
        except Exception as e:
            print(f"Error setting up database: {str(e)}")

    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        await self.process_commands(message)

def main():
    bot = EconomyBot()
    bot.load_extension('economy')
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()