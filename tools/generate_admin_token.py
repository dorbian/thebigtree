#!/usr/bin/env python3
"""
Quick script to generate an admin token for the dashboard.
Run this once to get your first admin token.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bigtree.inc import web_tokens
from datetime import datetime, timezone

def main():
    print("🌳 BigTree Admin Token Generator")
    print("=" * 50)
    
    # Get user input
    user_id = input("Enter your Discord User ID: ").strip()
    if not user_id or not user_id.isdigit():
        print("❌ Invalid user ID. Must be a number.")
        return
    
    user_name = input("Enter your display name (optional): ").strip() or "Admin"
    
    print("\nGenerating admin token with full access (admin:*)...")
    
    try:
        # Issue token with full admin access
        doc = web_tokens.issue_token(
            user_id=int(user_id),
            scopes=["admin:*"],  # Full admin access
            ttl_seconds=30 * 24 * 60 * 60,  # 30 days
            user_name=user_name,
        )
        
        token = doc["token"]
        expires_at = doc["expires_at"]
        
        if isinstance(expires_at, (int, float)):
            expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
            expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            expires_str = str(expires_at)
        
        print("\n" + "=" * 50)
        print("✅ SUCCESS! Admin token generated:")
        print("=" * 50)
        print(f"\nToken: {token}")
        print(f"\nUser: {user_name} ({user_id})")
        print(f"Scopes: admin:* (full access)")
        print(f"Expires: {expires_str}")
        print("\n" + "=" * 50)
        print("\n📋 Next steps:")
        print("1. Copy the token above")
        print("2. Use it in your API calls:")
        print(f'   curl -H "Authorization: Bearer {token}" http://localhost:8443/admin/tokens')
        print("\n3. Or visit the dashboard:")
        print("   http://localhost:8443/admin/dashboard")
        print("   (Set Authorization header in browser dev tools)")
        print("\n⚠️  Keep this token secure! It has full admin access.")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Error generating token: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
