"""
Custom Email Backend that can skip SSL verification (for expired certificates)

WARNING: Only use this for development when SSL certificate is expired!
For production, renew your SSL certificate instead.
"""
import ssl
from django.core.mail.backends.smtp import EmailBackend


class SSLIgnoreEmailBackend(EmailBackend):
    """
    Email backend that ignores SSL certificate verification errors.
    Useful when mail server has expired SSL certificate.
    """
    
    def open(self):
        if self.connection:
            return False
        
        try:
            import smtplib
            
            # Create connection
            if self.use_ssl:
                # Create SSL context that doesn't verify certificates
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                self.connection = smtplib.SMTP_SSL(
                    self.host, self.port,
                    timeout=self.timeout,
                    context=context
                )
            else:
                self.connection = smtplib.SMTP(
                    self.host, self.port,
                    timeout=self.timeout
                )
                
                # Handle STARTTLS
                if self.use_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    self.connection.starttls(context=context)
            
            # Authenticate
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            
            return True
            
        except Exception:
            if not self.fail_silently:
                raise
            return False
