import sys
from typing import List

import boto3
from asgiref.sync import sync_to_async

from consoleme.config import config
from consoleme.lib.generic import generate_html
from consoleme.lib.plugins import get_plugin_by_name

stats = get_plugin_by_name(config.get("plugins.metrics"))()
log = config.get_logger()


async def send_email(
    to_addresses: List[str],
    subject: str,
    body: str,
    sending_app: str = "consoleme",
    region: str = "us-west-2",
    charset: str = "UTF-8",
) -> None:
    client = boto3.client("ses", region_name=region)
    sender = config.get(f"ses.{sending_app}.sender")

    log_data = {
        "to_user": to_addresses,
        "region": region,
        "function": f"{__name__}.{sys._getframe().f_code.co_name}",
        "sender": sender,
    }

    if not config.get("ses.arn"):
        raise Exception(
            "Configuration value for `ses.arn` is not defined. Unable to send e-mail."
        )

    if config.get("development") and config.get("ses.override_receivers_for_dev"):
        log_data["original_to_addresses"] = to_addresses
        log_data["message"] = "Overriding to_address"
        to_addresses = config.get("ses.override_receivers_for_dev")
        log_data["new_to_addresses"] = to_addresses
        log.debug(log_data)

    try:
        response = await sync_to_async(client.send_email)(
            Destination={"ToAddresses": to_addresses},  # This should be a list
            Message={
                "Body": {
                    "Html": {"Charset": charset, "Data": body},
                    "Text": {"Charset": charset, "Data": body},
                },
                "Subject": {"Charset": charset, "Data": subject},
            },
            Source=sender,
            SourceArn=config.get("ses.arn"),
        )
    # Display an error if something goes wrong.
    except Exception:
        stats.count("lib.ses.error")
        log_data["message"] = "Exception sending email"
        log.error(log_data, exc_info=True)
    else:
        stats.count("lib.ses.success")
        log_data["message"] = "Email sent succesfully"
        log_data["response"] = response["MessageId"]
        log.debug(log_data)


async def send_access_email_to_user(
    user: str,
    group: str,
    updated_by: str,
    status: str,
    request_url: str,
    group_url: str,
    reviewer_comments: None = None,
    sending_app: str = "consoleme",
) -> None:
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: Request for group {group} has been {status}"
    to_addresses = [user, updated_by]
    group_link = f"<a href={group_url}>{group}</a>"
    message = f"Your request for group {group_link} has been {status} by {updated_by}."
    if status == "approved":
        message += " Please allow up to 30 minutes for your group to propagate. "

    reviewer_comments_section = ""
    if reviewer_comments:
        reviewer_comments_section = f"Reviewer Comments: {reviewer_comments}"
    body = f"""<html>
    <head>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    <title>Request Status</title>
    </head>
    <body>
    {message} <br>
    {reviewer_comments_section} <br>
    See your request here: {request_url}.<br>
    <br>
    {config.get('ses.support_reference', '')}
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    </body>
    </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)


async def send_request_created_to_user(
    user, group, updated_by, status, request_url, sending_app="consoleme"
):
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: Request for group {group} has been created"
    to_addresses = [user, updated_by]
    message = f"Your request for group {group} has been created."
    if status == "approved":
        message += " Please allow up to 30 minutes for your group to propagate. "
    body = f"""<html>
    <head>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    <title>Request Status</title>
    </head>
    <body>
    {message} <br>
    <br>
    See your request here: {request_url}.<br>
    <br>
    {config.get('ses.support_reference', '')}
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    </body>
    </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)


async def send_request_to_secondary_approvers(
    secondary_approvers,
    group,
    request_url,
    pending_requests_url,
    sending_app="consoleme",
):
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: A request for group {group} requires your approval"
    to_addresses = secondary_approvers
    message = f"A request for group {group} requires your approval."
    body = f"""<html>
        <head>
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        <title>Request Status</title>
        </head>
        <body>
        {message} <br>
        <br>
        See the request here: {request_url}.<br>
        <br>
        You can find all pending requests waiting your approval here: {pending_requests_url}. <br>
        <br>
        {config.get('ses.support_reference', '')}
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        </body>
        </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)


async def send_group_modification_notification(
    group, to_addresses, added_members, group_url, sending_app="consoleme"
):
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: Group {group} was modified"
    group_link = f"<a href={group_url}>{group}</a>"
    message = f"""Group {app_name} was modified.<br>
    You or a group you belong to are configured to receive a notification when new members are added to this group.<br>
    {group_link} admins may click the group link above to view and modify this configuration."""
    added_members_snippet = ""
    if added_members:
        added_members_snippet = f"""<b>Users added</b>: <br>
        {generate_html(added_members)}<br>
        """
    body = f"""<html>
        <head>
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        </head>
        <body>
         {message}<br>
         <br>
         {added_members_snippet}<br>
        <br>
        <br>
        {config.get('ses.support_reference', '')}
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        </body>
        </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)


async def send_new_aws_groups_notification(
    to_addresses, new_aws_groups, sending_app="consoleme"
):
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: New AWS groups detected"
    message = f"""New AWS login groups were created.<br>
    ConsoleMe is configured to send notifications when new AWS-related google groups are detected.
    This is to detect any accidentally or maliciously created google groups.<br>"""
    added_groups_snippet = ""
    if new_aws_groups:
        added_groups_snippet = f"""<b>New groups</b>: <br>
        {generate_html({"New Groups": new_aws_groups})}<br>
        """
    body = f"""<html>
        <head>
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        </head>
        <body>
         {message}<br>
         <br>
         {added_groups_snippet}<br>
        <br>
        <br>
        {config.get('ses.support_reference', '')}
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        </body>
        </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)


async def send_policy_request_to_approvers(
    request, policy_change_uri, pending_requests_url, sending_app="consoleme"
):
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: A policy change request for {request['arn']} requires your review."
    to_addresses = config.get("groups.can_admin_policies")
    if config.get("development"):
        to_addresses = config.get("groups.developement_notification_emails")
    message = f"A policy change request for {request['arn']} requires your review."
    body = f"""<html>
        <head>
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        <title>Policy Change Request Status</title>
        </head>
        <body>
        {message} <br>
        <br>
        See the request here: {policy_change_uri}.<br>
        <br>
        You can find all pending requests waiting your approval here: {pending_requests_url}. <br>
        <br>
        {config.get('ses.support_reference', '')}
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        </body>
        </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)


async def send_policy_request_status_update(
    request, policy_change_uri, sending_app="consoleme"
):
    app_name = config.get(f"ses.{sending_app}.name")
    subject = f"{app_name}: Policy change request for {request['arn']} has been {request['status']}"
    to_addresses = [request.get("username")]
    message = (
        f"A policy change request for {request['arn']} has been {request['status']}"
    )
    if {request["status"]} == "approved":
        message += " and committed"
        subject += " and committed"
    body = f"""<html>
            <head>
            <meta http-equiv="content-type" content="text/html; charset=UTF-8">
            <title>Policy Change Request Status Change</title>
            </head>
            <body>
            {message} <br>
            <br>
            See the request here: {policy_change_uri}.<br>
            <br>
            <br>
            {config.get('ses.support_reference', '')}
            <meta http-equiv="content-type" content="text/html; charset=UTF-8">
            </body>
            </html>"""
    await send_email(to_addresses, subject, body, sending_app=sending_app)