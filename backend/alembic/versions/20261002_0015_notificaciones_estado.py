"""notification config per work order status + outbox
Revision ID: 20261002_0015
Revises: 20261002_0014
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0015"
down_revision = "20261002_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "work_order_statuses",
        sa.Column("notify_whatsapp", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "work_order_statuses",
        sa.Column("notify_email", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "work_order_statuses",
        sa.Column("notifications_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("work_order_statuses", sa.Column("notification_template", sa.Text(), nullable=True))
    op.add_column(
        "work_order_statuses",
        sa.Column("notification_email_subject", sa.String(200), nullable=True),
    )

    # Instancia de la gateway de WhatsApp y remitente propio. La autenticacion (API key y
    # SMTP) es de plataforma: no se guardan credenciales por empresa.
    op.add_column("companies", sa.Column("whatsapp_instance_id", sa.String(80), nullable=True))
    op.add_column("companies", sa.Column("notification_sender_name", sa.String(120), nullable=True))
    op.add_column("companies", sa.Column("notification_sender_email", sa.String(255), nullable=True))

    op.create_table(
        "work_order_notifications",
        # Idempotencia: un evento de cambio de estado genera a lo sumo una notificacion por
        # canal. Por eso work_order_event_id es NOT NULL: si fuera nullable, en SQL los
        # NULL no se consideran iguales y la deduplicacion fallaria en silencio.
        sa.UniqueConstraint(
            "company_id", "work_order_event_id", "channel", name="uq_wo_notif_event_channel"
        ),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_event_id", sa.Integer(), sa.ForeignKey("work_order_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("provider_message_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_work_order_notifications_company_id", "work_order_notifications", ["company_id"])
    op.create_index("ix_work_order_notifications_work_order_id", "work_order_notifications", ["work_order_id"])
    op.create_index("ix_work_order_notifications_status", "work_order_notifications", ["status"])


def downgrade():
    op.drop_table("work_order_notifications")
    op.drop_column("companies", "notification_sender_email")
    op.drop_column("companies", "notification_sender_name")
    op.drop_column("companies", "whatsapp_instance_id")
    op.drop_column("work_order_statuses", "notification_email_subject")
    op.drop_column("work_order_statuses", "notification_template")
    op.drop_column("work_order_statuses", "notifications_active")
    op.drop_column("work_order_statuses", "notify_email")
    op.drop_column("work_order_statuses", "notify_whatsapp")
