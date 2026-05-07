"""
Professional Email Templates for Cheradip
Branded emails with logo and proper formatting to avoid spam filters
"""

def get_verification_email(code, user_name="User"):
    """Generate verification email HTML"""
    
    subject = "Cheradip - Verify Your Account"
    logo_img = "https://cheradip.com/assets/images/logo.jpg"
    
    html_content = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Your Cheradip Account</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f4f8;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f4f8; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden;">
                    
                    <!-- Header with Logo -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 35px 30px; text-align: center; border-bottom: 3px solid #008080;">
                            <img src="{logo_img}" alt="Cheradip" style="max-width: 180px; height: auto; margin-bottom: 12px;" />
                            <p style="color: #008080; margin: 0; font-size: 15px; font-weight: 500; letter-spacing: 0.5px;">
                                Spreading The Light Of Knowledge!
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Main Content -->
                    <tr>
                        <td style="padding: 40px 35px;">
                            <h2 style="color: #1a1a2e; margin: 0 0 20px 0; font-size: 24px; font-weight: 600;">
                                Hello {user_name}! 👋
                            </h2>
                            
                            <p style="color: #4a4a4a; font-size: 16px; line-height: 1.7; margin: 0 0 25px 0;">
                                Thank you for joining <strong style="color: #008080;">Cheradip</strong>! To complete your registration, 
                                please use the verification code below:
                            </p>
                            
                            <!-- Verification Code Box -->
                            <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 2px solid #008080; border-radius: 12px; padding: 28px; text-align: center; margin: 30px 0;">
                                <p style="color: #666; margin: 0 0 12px 0; font-size: 13px; text-transform: uppercase; letter-spacing: 2px; font-weight: 600;">
                                    Your Verification Code
                                </p>
                                <p style="color: #008080; font-size: 40px; font-weight: bold; letter-spacing: 10px; margin: 0; font-family: 'Courier New', monospace; user-select: all; cursor: pointer;">
                                    {code}
                                </p>
                                <p style="color: #888; margin: 15px 0 0 0; font-size: 13px;">
                                    This code expires in <strong>10 minutes</strong>
                                </p>
                            </div>
                            
                            <p style="color: #777; font-size: 14px; line-height: 1.6; margin: 25px 0 0 0;">
                                If you didn't create an account on Cheradip, you can safely ignore this email.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- About Cheradip Section -->
                    <tr>
                        <td style="background-color: #f8fafa; padding: 25px 35px; border-top: 1px solid #e8e8e8;">
                            <h3 style="color: #008080; margin: 0 0 15px 0; font-size: 16px; font-weight: 600;">
                                About Cheradip
                            </h3>
                            <p style="color: #555; font-size: 14px; line-height: 1.6; margin: 0;">
                                <strong>Cheradip</strong> is Bangladesh's leading education platform providing:
                            </p>
                            <ul style="color: #555; font-size: 14px; line-height: 1.9; margin: 12px 0; padding-left: 20px;">
                                <li>MCQ Practice for HSC, SSC & Admission Tests</li>
                                <li>School & College Information Database</li>
                                <li>Merit Lists & Vacancy Information</li>
                                <li>Quality Education Resources for Everyone</li>
                            </ul>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 35px 30px; border-top: 3px solid #008080; text-align: center;">
                            <img src="{logo_img}" alt="Cheradip" style="max-width: 120px; height: auto; margin-bottom: 12px;" />
                            <p style="color: #008080; font-size: 15px; font-weight: 500; margin: 0 0 10px 0;">
                                Spreading The Light Of Knowledge!
                            </p>
                            <p style="margin: 0 0 10px 0;">
                                <a href="https://cheradip.com" style="color: #008080; text-decoration: none; font-size: 14px; font-weight: 500;">cheradip.com</a> | <a href="https://wa.me/8801722710298" style="color: #008080; text-decoration: none; font-size: 14px; font-weight: 500;">+8801722710298</a>
                            </p>
                            <p style="color: #555; font-size: 13px; margin: 0 0 8px 0;">
                                Bangladesh's education platform for MCQ practice, school info & merit lists.
                            </p>
                            <p style="color: #999; font-size: 12px; margin: 15px 0 0 0;">
                                © 2024 Cheradip Education. All rights reserved.
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
'''
    
    text_content = f'''
Hello {user_name}!

Thank you for joining Cheradip!

Your verification code is: {code}

This code will expire in 10 minutes.

If you didn't create an account on Cheradip, you can safely ignore this email.

---
About Cheradip:
Cheradip is Bangladesh's leading education platform providing MCQ practice, 
school information, merit lists, and quality education resources.

"Spreading The Light Of Knowledge!"

---
Contact Us:
Email: support@cheradip.com
Phone: +8801722710298
Website: https://cheradip.com

© 2024 Cheradip Education. All rights reserved.
'''
    
    return subject, text_content, html_content


def get_password_reset_email(code, user_name="User"):
    """Generate password reset email HTML"""
    
    subject = "Cheradip - Reset Your Password"
    logo_img = "https://cheradip.com/assets/images/logo.jpg"
    profile_img = "https://cheradip.com/assets/images/logo3.jpg"
    
    html_content = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Cheradip Password</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f4f8;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f0f4f8; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden;">
                    
                    <!-- Header with Logo -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 35px 30px; text-align: center; border-bottom: 3px solid #e74c3c;">
                            <img src="{logo_img}" alt="Cheradip" style="max-width: 180px; height: auto; margin-bottom: 12px;" />
                            <h2 style="color: #e74c3c; margin: 10px 0 0 0; font-size: 20px; font-weight: 600;">
                                🔐 Password Reset Request
                            </h2>
                            <p style="color: #008080; margin: 8px 0 0 0; font-size: 14px; font-weight: 500;">
                                Spreading The Light Of Knowledge!
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Main Content -->
                    <tr>
                        <td style="padding: 40px 35px;">
                            <h2 style="color: #1a1a2e; margin: 0 0 20px 0; font-size: 24px; font-weight: 600;">
                                Hello {user_name}! 👋
                            </h2>
                            
                            <p style="color: #4a4a4a; font-size: 16px; line-height: 1.7; margin: 0 0 25px 0;">
                                We received a request to reset your <strong style="color: #008080;">Cheradip</strong> account password. 
                                Use the code below to set a new password:
                            </p>
                            
                            <!-- Reset Code Box -->
                            <div style="background: linear-gradient(135deg, #fff5f5 0%, #ffe8e8 100%); border: 2px solid #e74c3c; border-radius: 12px; padding: 28px; text-align: center; margin: 30px 0;">
                                <p style="color: #666; margin: 0 0 12px 0; font-size: 13px; text-transform: uppercase; letter-spacing: 2px; font-weight: 600;">
                                    Password Reset Code
                                </p>
                                <p style="color: #e74c3c; font-size: 40px; font-weight: bold; letter-spacing: 10px; margin: 0; font-family: 'Courier New', monospace; user-select: all; cursor: pointer;">
                                    {code}
                                </p>
                                <p style="color: #888; margin: 15px 0 0 0; font-size: 13px;">
                                    This code expires in <strong>10 minutes</strong>
                                </p>
                            </div>
                            
                            <div style="background-color: #fff8e1; border-left: 4px solid #ffc107; padding: 15px 18px; margin: 25px 0; border-radius: 0 8px 8px 0;">
                                <p style="color: #856404; font-size: 14px; margin: 0; line-height: 1.6;">
                                    <strong>⚠️ Security Notice:</strong> If you didn't request this password reset, 
                                    please ignore this email. Your password will remain unchanged.
                                </p>
                            </div>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 35px 30px; border-top: 3px solid #008080; text-align: center;">
                            <img src="{logo_img}" alt="Cheradip" style="max-width: 120px; height: auto; margin-bottom: 12px;" />
                            <p style="color: #008080; font-size: 15px; font-weight: 500; margin: 0 0 10px 0;">
                                Spreading The Light Of Knowledge!
                            </p>
                            <p style="margin: 0 0 10px 0;">
                                <a href="https://cheradip.com" style="color: #008080; text-decoration: none; font-size: 14px; font-weight: 500;">cheradip.com</a> | <a href="https://wa.me/8801722710298" style="color: #008080; text-decoration: none; font-size: 14px; font-weight: 500;">+8801722710298</a>
                            </p>
                            <p style="color: #999; font-size: 12px; margin: 15px 0 0 0;">
                                © 2024 Cheradip Education. All rights reserved.
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
'''
    
    text_content = f'''
Hello {user_name}!

We received a request to reset your Cheradip password.

Your password reset code is: {code}

This code will expire in 10 minutes.

SECURITY NOTICE: If you didn't request this password reset, please ignore this email. 
Your password will remain unchanged.

---
Contact Us:
Email: support@cheradip.com
Phone: +8801722710298
Website: https://cheradip.com

Cheradip - Spreading The Light Of Knowledge!
© 2024 Cheradip Education. All rights reserved.
'''
    
    return subject, text_content, html_content
