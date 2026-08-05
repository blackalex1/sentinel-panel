import argparse
import asyncio
import sys
from backend.node_agent import register_with_master

def main():
    parser = argparse.ArgumentParser(description="Spectre Panel Edge Node Registration Utility")
    parser.add_argument(
        "--master", 
        required=True, 
        help="Master Server URL (e.g., https://master-server.com/secret_path)"
    )
    parser.add_argument(
        "--join-code", 
        required=True, 
        help="One-time join code generated on the Master Server (e.g., JOIN-A7F9B2)"
    )
    
    args = parser.parse_args()
    
    print(f"[*] Starting Edge Node registration...")
    print(f"[*] Master URL: {args.master}")
    print(f"[*] Join Code:  {args.join_code}")
    
    # Run async registration
    try:
        success = asyncio.run(register_with_master(args.master, args.join_code))
        if success:
            print("[+] Success: Node registered successfully! Configuration saved to node_config.json")
            sys.exit(0)
        else:
            print("[-] Error: Registration failed. Please check the Master URL, join code, and network connection.")
            sys.exit(1)
    except Exception as e:
        print(f"[-] Error: Exception during registration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
