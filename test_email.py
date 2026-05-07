"""Test email sending via cPanel (support@cheradip.com)"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from cheradip.email_templates import get_verification_email

print("=" * 60)
print("CHERADIP EMAIL TEST (cPanel)")
print("=" * 60)

print(f"\nFrom: {settings.EMAIL_HOST_USER}")
print(f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")

# Test verification email
subject, text_content, html_content = get_verification_email("847291", "Sashafik")
to_email = 'sashafik.me@gmail.com'
from_email = f'Cheradip <{settings.EMAIL_HOST_USER}>'

print(f"To: {to_email}")
print(f"\nSending...")

try:
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=[to_email]
    )
    email.attach_alternative(html_content, 'text/html')
    result = email.send(fail_silently=False)
    
    print(f"\n[SUCCESS] Email sent!")
    print(f"\nCheck your SPAM folder at {to_email}")
    print("(Emails may go to spam until domain reputation improves)")
    
except Exception as e:
    print(f"\n[FAILED] {type(e).__name__}: {e}")
