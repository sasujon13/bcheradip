"""Manual SMTP check. Importing this module never sends email."""


def main():
    import os
    import django

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    django.setup()

    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from cheradip.email_templates import get_verification_email

    subject, text_content, html_content = get_verification_email('847291', 'Sashafik')
    to_email = 'sashafik.me@gmail.com'
    from_email = f'Cheradip <{settings.EMAIL_HOST_USER}>'
    print(f'Manual email test: {settings.EMAIL_HOST_USER} -> {to_email}')
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=[to_email],
    )
    email.attach_alternative(html_content, subtype='html')
    email.send(fail_silently=False)
    print('Email sent.')


if __name__ == '__main__':
    main()
