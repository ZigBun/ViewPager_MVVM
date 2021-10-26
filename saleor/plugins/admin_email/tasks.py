from ...celeryconf import app
from ...csv.events import export_failed_info_sent_event, export_file_sent_event
from ...graphql.core.utils import from_global_id_or_none
from ..email_common import EmailConfig, send_email


@app.task(compression="zlib")
def send_set_staff_password_email_task(
    recipient_email, payload, config: dict, subject, template
):
    email_config = EmailConfig(**config)
    send_email(
        config=email_config,
        recipient_list=[recipient_email],
        context=payload,
        subject=subject,
        template_str=template,
    )


@app.task(compression="zlib")
def send_email_with_link_to_download_file_task(
    recipient_email: str, payload, config: dict, subject, template
):
 