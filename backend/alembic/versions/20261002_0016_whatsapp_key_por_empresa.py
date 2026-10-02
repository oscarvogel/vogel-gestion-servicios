"""per-company WhatsApp credentials
Revision ID: 20261002_0016
Revises: 20261002_0015
"""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0016"
down_revision = "20261002_0015"
branch_labels = None
depends_on = None


def upgrade():
    # La API key de la gateway se guarda por empresa, cifrada con Fernet. Nunca en claro:
    # es la credencial con la que la empresa habla con WhatsApp.
    op.add_column("companies", sa.Column("whatsapp_api_key_encrypted", sa.Text(), nullable=True))
    # Opt-in explicito a la key y la instancia de plataforma, para los talleres que no
    # tienen WhatsApp propio. Apagado por defecto: sin esto, una empresa sin key propia
    # fallaria en vez de mandar desde el numero de otro.
    op.add_column(
        "companies",
        sa.Column("whatsapp_use_platform_key", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("companies", "whatsapp_use_platform_key")
    op.drop_column("companies", "whatsapp_api_key_encrypted")
