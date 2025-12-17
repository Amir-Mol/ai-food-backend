import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio

async def send_verification_email(to_email: str, verification_code: str):
    """
    Sends a verification email using CSC Rahti's internal SMTP server.
    """
    # Rahti internal SMTP settings
    smtp_host = "smtp.rahti.csc.fi"
    smtp_port = 25  # Port 25 is standard for internal unauthenticated relay
    
    sender_email = os.environ.get("SENDER_EMAIL", "noreply@nutrirecom.com")

    # Create the email message
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = "Your NutriRecom Verification Code"

    html_content = f"""
    <html>
        <body>
            <p>Thank you for registering with NutriRecom.</p>
            <p>Your verification code is: <strong>{verification_code}</strong></p>
            <p>This code will expire in 10 minutes.</p>
            <p><i>Note: This is an automated message from the NutriRecom Research Project.</i></p>
        </body>
    </html>
    """
    
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Run the blocking SMTP call in a separate thread to avoid blocking FastAPI
        await asyncio.to_thread(_send_smtp_email, smtp_host, smtp_port, sender_email, to_email, msg)
        print(f"DEBUG: Email sent successfully to {to_email}")
    except Exception as e:
        print(f"ERROR: Failed to send email to {to_email}. Error: {e}")

def _send_smtp_email(host, port, sender, recipient, message):
    """Helper function to run SMTP interaction synchronously."""
    with smtplib.SMTP(host, port) as server:
        # No login() needed for Rahti internal SMTP
        server.sendmail(sender, recipient, message.as_string())