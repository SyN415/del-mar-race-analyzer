#!/usr/bin/env python3
"""
Test 2Captcha Configuration
This script tests your 2Captcha API key and account configuration
"""

import os
import sys
from twocaptcha import TwoCaptcha
from twocaptcha.api import ApiException

def test_2captcha_config():
    """Test 2Captcha API configuration"""
    
    print("=" * 60)
    print("2Captcha Configuration Test")
    print("=" * 60)
    print()
    
    # Get API key from environment
    api_key = os.environ.get('TWOCAPTCHA_API_KEY')
    
    if not api_key:
        print("❌ ERROR: TWOCAPTCHA_API_KEY environment variable not set")
        print()
        print("Set it with:")
        print("  export TWOCAPTCHA_API_KEY='your_api_key_here'")
        return False
    
    print(f"✅ API Key found: {api_key[:8]}...{api_key[-4:]}")
    print(f"   Length: {len(api_key)} characters")
    
    if len(api_key) != 32:
        print(f"⚠️  WARNING: API key should be 32 characters, got {len(api_key)}")
    
    print()
    
    # Initialize solver
    try:
        solver = TwoCaptcha(api_key)
        print("✅ TwoCaptcha solver initialized")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize solver: {e}")
        return False
    
    print()
    
    # Test 1: Check balance
    print("Test 1: Checking account balance...")
    try:
        balance = solver.balance()
        print(f"✅ Balance check successful: ${balance:.4f}")
        
        if balance < 0.01:
            print(f"⚠️  WARNING: Low balance (${balance:.4f})")
            print("   Add funds at: https://2captcha.com/enterpage")
        elif balance < 0.50:
            print(f"⚠️  Balance is low (${balance:.4f}), consider adding more funds")
        else:
            print(f"✅ Balance is sufficient (${balance:.4f})")
    except ApiException as e:
        print(f"❌ ERROR: Balance check failed: {e}")
        print(f"   Error code: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: Unexpected error checking balance: {e}")
        return False
    
    print()
    
    # Test 2: Try solving a test hCaptcha
    print("Test 2: Testing hCaptcha solving with 2Captcha demo...")
    print("   This will cost ~$0.003 from your balance")
    print("   Using 2Captcha's official demo hCaptcha")
    
    try:
        # Use 2Captcha's official demo hCaptcha
        test_sitekey = '10000000-ffff-ffff-ffff-000000000001'
        test_url = 'https://2captcha.com/demo/hcaptcha'
        
        print(f"   Sitekey: {test_sitekey}")
        print(f"   URL: {test_url}")
        print("   Sending to 2Captcha API...")
        
        result = solver.hcaptcha(
            sitekey=test_sitekey,
            url=test_url
        )
        
        if result and result.get('code'):
            token = result['code']
            print(f"✅ hCaptcha solved successfully!")
            print(f"   Token: {token[:50]}...")
            print(f"   Token length: {len(token)} characters")
            return True
        else:
            print(f"❌ ERROR: No token returned")
            print(f"   Result: {result}")
            return False
            
    except ApiException as e:
        error_code = str(e)
        print(f"❌ ERROR: hCaptcha solving failed")
        print(f"   Error code: {error_code}")
        print()
        
        # Provide specific guidance based on error
        if "ERROR_METHOD_CALL" in error_code:
            print("📖 ERROR_METHOD_CALL means:")
            print("   1. hCaptcha solving is not enabled in your account")
            print("   2. Your account type doesn't support hCaptcha")
            print("   3. Invalid parameters (but we're using standard params)")
            print()
            print("🔧 How to fix:")
            print("   1. Go to: https://2captcha.com/setting")
            print("   2. Scroll to 'Captcha Types' section")
            print("   3. Make sure 'hCaptcha' is checked/enabled")
            print("   4. Save settings")
            print("   5. If still not working, contact 2Captcha support")
            print("      Support: https://2captcha.com/support")
            
        elif "ERROR_ZERO_BALANCE" in error_code:
            print("📖 ERROR_ZERO_BALANCE means:")
            print("   Your account has insufficient funds")
            print()
            print("🔧 How to fix:")
            print("   Add funds at: https://2captcha.com/enterpage")
            
        elif "ERROR_WRONG_USER_KEY" in error_code or "ERROR_KEY_DOES_NOT_EXIST" in error_code:
            print("📖 Invalid API key")
            print()
            print("🔧 How to fix:")
            print("   1. Go to: https://2captcha.com/enterpage")
            print("   2. Copy your API key (should be 32 characters)")
            print("   3. Update TWOCAPTCHA_API_KEY environment variable")
            
        else:
            print(f"📖 Unknown error: {error_code}")
            print()
            print("🔧 Next steps:")
            print("   1. Check 2Captcha service status: https://2captcha.com/status")
            print("   2. Contact 2Captcha support: https://2captcha.com/support")
        
        return False
        
    except Exception as e:
        print(f"❌ ERROR: Unexpected error: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    print()
    success = test_2captcha_config()
    print()
    print("=" * 60)
    
    if success:
        print("✅ ALL TESTS PASSED")
        print()
        print("Your 2Captcha configuration is working correctly!")
        print("The ERROR_METHOD_CALL in production might be due to:")
        print("  1. Different hCaptcha type on Equibase (enterprise vs regular)")
        print("  2. Additional parameters needed for Equibase's specific hCaptcha")
        print("  3. Rate limiting or temporary API issues")
    else:
        print("❌ TESTS FAILED")
        print()
        print("Fix the issues above before using in production.")
        print("See the error messages for specific guidance.")
    
    print("=" * 60)
    print()
    
    sys.exit(0 if success else 1)

