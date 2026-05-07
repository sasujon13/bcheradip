"""
Free Verification Service for Cheradip

Priority:
1. Email (if user has email) - FREE via Gmail
2. WhatsApp (fallback) - FREE via CallMeBot API

Setup Instructions:
-------------------

1. EMAIL (FREE via Gmail - Primary):
   a) Enable 2FA on Gmail
   b) Create App Password: Google Account > Security > App Passwords
   c) Add to .env:
      EMAIL_HOST_USER=your_email@gmail.com
      EMAIL_HOST_PASSWORD=your_app_password

2. WHATSAPP (FREE via CallMeBot - Fallback):
   Users need to activate once:
   a) Add phone +34 644 51 95 23 to contacts
   b) Send "I allow callmebot to send me messages" to that number on WhatsApp
   c) Done! They can now receive verification codes
   
   No server configuration needed - it's completely free!
"""

import random
import string
import logging
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from decouple import config
import requests

logger = logging.getLogger(__name__)


class VerificationService:
    """Email + WhatsApp verification service (100% FREE)"""
    
    def __init__(self):
        self.email_configured = bool(config('EMAIL_HOST_USER', default=''))
    
    def generate_code(self, length=6):
        """Generate a random numeric verification code"""
        return ''.join(random.choices(string.digits, k=length))
    
    def send_verification(self, user, code, purpose='verification'):
        """
        Send verification code - tries Email first, then WhatsApp
        
        Args:
            user: Customer model instance
            code: Verification code
            purpose: 'verification' or 'password_reset'
            
        Returns:
            dict: {'success': bool, 'message': str, 'method': str}
        """
        email = getattr(user, 'email', None)
        
        # Try Email first if user has email
        if email:
            result = self._send_via_email(user, code, purpose)
            if result['success']:
                return result
        
        # Fallback to WhatsApp
        return self._send_via_whatsapp(user, code, purpose)
    
    # =========================================================================
    # EMAIL (FREE via Gmail)
    # =========================================================================
    
    def _send_via_email(self, user, code, purpose):
        """Send via Email using cPanel (support@cheradip.com)"""
        try:
            email = getattr(user, 'email', None)
            
            if not email:
                return {
                    'success': False,
                    'message': 'No email address found',
                    'method': 'email',
                    'needs_email': True
                }
            
            # Use professional email templates
            from .email_templates import get_verification_email, get_password_reset_email
            from django.core.mail import EmailMultiAlternatives
            
            user_name = getattr(user, 'fullName', 'User') or 'User'
            
            if purpose == 'password_reset':
                subject, plain_message, html_message = get_password_reset_email(code, user_name)
            else:
                subject, plain_message, html_message = get_verification_email(code, user_name)
            
            # Send via cPanel email
            email_msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_message,
                from_email=f'Cheradip <{settings.EMAIL_HOST_USER}>',
                to=[email]
            )
            email_msg.attach_alternative(html_message, "text/html")
            email_msg.send(fail_silently=False)
            
            # Mask email for display
            masked_email = email[:3] + '***@' + email.split('@')[1]
            
            logger.info(f"Email sent to {masked_email}")
            return {
                'success': True,
                'message': f'Code sent to {masked_email} (check spam folder)',
                'method': 'email'
            }
            
        except Exception as e:
            logger.error(f"Email error: {str(e)}")
            return {
                'success': False,
                'message': f'Email failed: {str(e)}',
                'method': 'email'
            }
    
    # =========================================================================
    # WHATSAPP (FREE via CallMeBot)
    # =========================================================================
    
    def _send_via_whatsapp(self, user, code, purpose):
        """
        Send via WhatsApp using CallMeBot API - 100% FREE
        
        User must activate once by:
        1. Add +34 644 51 95 23 to contacts
        2. Send "I allow callmebot to send me messages" via WhatsApp
        
        Get API key from the response message.
        """
        try:
            phone = user.username
            whatsapp_apikey = getattr(user, 'whatsapp_apikey', None)
            
            # Format phone number
            phone_formatted = self._format_phone_for_whatsapp(phone)
            
            if not whatsapp_apikey:
                # User hasn't activated CallMeBot yet
                return {
                    'success': False,
                    'message': 'WhatsApp not activated. Please add your email or activate WhatsApp.',
                    'method': 'whatsapp',
                    'needs_activation': True,
                    'activation_instructions': {
                        'step1': 'Add +34 644 51 95 23 to your WhatsApp contacts',
                        'step2': 'Send this message: "I allow callmebot to send me messages"',
                        'step3': 'You will receive an API key - save it in your profile'
                    }
                }
            
            # Prepare message
            if purpose == 'password_reset':
                message = f"🔐 *Cheradip Password Reset*\n\nYour code: *{code}*\n\nExpires in 10 minutes."
            else:
                message = f"✅ *Cheradip Verification*\n\nYour code: *{code}*\n\nExpires in 10 minutes."
            
            # Send via CallMeBot API (FREE)
            url = "https://api.callmebot.com/whatsapp.php"
            params = {
                'phone': phone_formatted,
                'text': message,
                'apikey': whatsapp_apikey
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200 and 'Message queued' in response.text:
                logger.info(f"WhatsApp sent to {phone}")
                return {
                    'success': True,
                    'message': 'Code sent to your WhatsApp',
                    'method': 'whatsapp'
                }
            else:
                logger.error(f"CallMeBot error: {response.text}")
                return {
                    'success': False,
                    'message': 'WhatsApp delivery failed. Please use email instead.',
                    'method': 'whatsapp'
                }
                
        except Exception as e:
            logger.error(f"WhatsApp error: {str(e)}")
            return {
                'success': False,
                'message': f'WhatsApp failed: {str(e)}',
                'method': 'whatsapp'
            }
    
    def _format_phone_for_whatsapp(self, phone):
        """Format phone for WhatsApp (with country code, no + or 0)"""
        # Remove any non-digit characters
        phone = ''.join(filter(str.isdigit, str(phone)))
        
        # Bangladesh number handling
        if len(phone) == 11 and phone.startswith('0'):
            phone = '880' + phone[1:]  # Remove leading 0, add 880
        elif len(phone) == 10:
            phone = '880' + phone
        elif phone.startswith('880'):
            pass  # Already has country code
        
        return phone


# Singleton instance
verification_service = VerificationService()


def send_verification_code(customer, purpose='verification'):
    """
    Generate and send verification code to customer
    
    Args:
        customer: Customer model instance
        purpose: 'verification' or 'password_reset'
        
    Returns:
        dict: Result with success status and message
    """
    code = verification_service.generate_code()
    
    # Save code to customer record
    customer.verification_code = code
    customer.verification_code_expires = timezone.now() + timedelta(minutes=10)
    customer.save(update_fields=['verification_code', 'verification_code_expires'])
    
    # Send via Email (primary) or WhatsApp (fallback)
    result = verification_service.send_verification(customer, code, purpose)
    
    return result


def verify_code(customer, code):
    """
    Verify the code entered by user
    
    Args:
        customer: Customer model instance
        code: Code entered by user
        
    Returns:
        dict: {'success': bool, 'message': str}
    """
    if not customer.verification_code:
        return {'success': False, 'message': 'No verification code found. Please request a new code.'}
    
    if customer.verification_code_expires and timezone.now() > customer.verification_code_expires:
        return {'success': False, 'message': 'Code expired. Please request a new code.'}
    
    if customer.verification_code != code:
        return {'success': False, 'message': 'Invalid code. Please try again.'}
    
    # Code is valid
    customer.whatsapp_verified = True
    customer.verification_code = None
    customer.verification_code_expires = None
    customer.save(update_fields=['whatsapp_verified', 'verification_code', 'verification_code_expires'])
    
    return {'success': True, 'message': 'Verified successfully!'}


def send_verification_to_email(customer, email, purpose='password_reset'):
    """
    Send verification to a specific email (for users adding email during password reset)
    
    Args:
        customer: Customer model instance
        email: Email address to send to
        purpose: Purpose of verification
        
    Returns:
        dict: Result
    """
    code = verification_service.generate_code()
    
    # Temporarily set email for sending
    original_email = customer.email
    customer.email = email
    
    # Save code
    customer.verification_code = code
    customer.verification_code_expires = timezone.now() + timedelta(minutes=10)
    customer.save(update_fields=['verification_code', 'verification_code_expires'])
    
    # Send
    result = verification_service._send_via_email(customer, code, purpose)
    
    # Restore original email (don't save yet - only save after verification)
    customer.email = original_email
    
    return result
