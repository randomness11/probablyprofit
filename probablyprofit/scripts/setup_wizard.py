
import os
import sys

# Add parent dir to path to find probablyprofit
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.constants import POLYGON
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    print("⚠️  py-clob-client not found. Install with: pip install -e .")

def setup_wizard():
    print("🤖 Welcome to Poly16z Setup Wizard!")
    print("-----------------------------------")
    print("This script will help you create your .env configuration file.")
    print("We can automatically generate your Polymarket API Keys using your Private Key.")
    print("")

    # 1. Private Key (Wallet)
    print("🔑 WALLET CONFIGURATION")
    print("Paste your Polygon Private Key (starts with 0x).")
    print("NOTE: This key is stored LOCALLY in .env only. Never share it.")
    pk = input("Private Key: ").strip()
    
    poly_key = ""
    poly_secret = ""
    poly_pass = ""

    if not pk:
        print("⚠️  No private key provided. You will run in READ-ONLY mode.")
    elif CLOB_AVAILABLE:
        print("\n🔄 Deriving Polymarket API Credentials from Private Key...")
        try:
            # Initialize client with PK to derive keys
            # We use a mutable client or just the helper if available, 
            # but ClobClient does this in init/derive.
            # Using chain_id=137 (Polygon)
            client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
            creds = client.create_or_derive_api_key()
            
            poly_key = creds.api_key
            poly_secret = creds.api_secret
            poly_pass = creds.api_passphrase
            print("✅ Successfully generated API Keys!")
            print(f"   Key: {poly_key[:10]}...")
        except Exception as e:
            print(f"❌ Failed to derive keys: {e}")
            print("You may need to manually enter them or check if your PK has funds/gas (though not strictly needed for derivation).")
            poly_key = input("Polymarket API Key (optional): ").strip()
            poly_secret = input("Polymarket API Secret (optional): ").strip()
            poly_pass = input("Polymarket API Passphrase (optional): ").strip()
    else:
        print("⚠️  Cannot derive keys without py-clob-client.")
        
    # 2. AI Keys
    print("\n🧠 AI CONFIGURATION")
    openai_key = input("Enter OpenAI API Key (sk-...): ").strip()
    gemini_key = input("Enter Google Gemini API Key: ").strip()
    anthropic_key = input("Enter Anthropic API Key: ").strip()
    
    # 3. Generate .env content
    env_content = f"""# Poly16z Configuration

# Wallet
PRIVATE_KEY={pk}

# Polymarket CLOB API (Derived automatically)
POLYMARKET_API_KEY={poly_key}
POLYMARKET_API_SECRET={poly_secret}
POLYMARKET_API_PASSPHRASE={poly_pass}

# AI Providers
OPENAI_API_KEY={openai_key}
GOOGLE_API_KEY={gemini_key}
ANTHROPIC_API_KEY={anthropic_key}

# Risk Settings
# Max dollars to lose in a day
MAX_DAILY_LOSS=50.0
# Max dollars per position
MAX_POSITION_SIZE=20.0
"""

    # 4. Write to file
    if os.path.exists(".env"):
        overwrite = input("\n⚠️  .env file already exists. Overwrite? (y/n): ").lower()
        if overwrite != 'y':
            print("Aborted.")
            return

    with open(".env", "w") as f:
        f.write(env_content)
    
    print("\n✅ Success! .env file created.")
    print("You can now run the bot using: python main.py")

if __name__ == "__main__":
    setup_wizard()
