class BotConfig:
    # Initial balance for new users
    INITIAL_BALANCE = 100
    
    # Message reward formula (will be evaluated with message length)
    # Use %length% as placeholder for message length
    MESSAGE_REWARD_FORMULA = "%length% * 3"
    
    # Daily command configuration
    DAILY_MIN_AMOUNT = 100
    DAILY_MAX_AMOUNT = 1000
    
    # Admin confirmation code for /set command
    ADMIN_CODE = "1234"