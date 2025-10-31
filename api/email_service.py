import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import asyncio


async def send_verification_email(to_email: str, verification_code: str):
    """
    Sends a verification email to the user with a verification code using SendGrid.
    """
    sendgrid_api_key = os.environ.get("SENDGRID_API_KEY")
    sender_email = os.environ.get("SENDER_EMAIL")

    if not sendgrid_api_key or not sender_email:
        print("Error: SENDGRID_API_KEY or SENDER_EMAIL not set in environment variables.")
        # In a real application, you might want to raise an exception here.
        return

    message = Mail(
        from_email=sender_email,
        to_emails=to_email,
        subject="Your NutriRecom Verification Code",
        html_content=f"<p>Thank you for registering with NutriRecom.</p><p>Your verification code is: <strong>{verification_code}</strong></p><p>This code will expire in 10 minutes.</p>"
    )
    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        await asyncio.to_thread(sg.client.mail.send.post, request_body=message.get())
    except Exception as e:
        print(f"An error occurred while sending email: {e}")