"""propuestas de acciones de la IA

Revision ID: 20261003_0021
Revises: 20261003_0020

La regla de #44 sub-issue 3: **la IA propone, la persona confirma**. Y queda registro de quien
propuso, quien confirmo o corrigio, y que se termino persistiendo.

Esta tabla es ese registro, y tambien el candado: una propuesta se aplica **una sola vez**. El
estado pasa de `pendiente` a `aplicada` con un update condicional, asi que un doble clic o un
reintento del navegador no puede escribir dos veces. No hace falta una clave de idempotencia
en el contenido: la propia propuesta es la clave.

Lo que se guarda, porque sin esto una accion hecha "por IA" no se puede auditar:

- `proposed_arguments`: lo que propuso el modelo, literal.
- `confirmed_arguments`: lo que la persona confirmo o corrigio. **Es lo que se escribe**, y
  puede ser distinto de lo propuesto: esa diferencia es justamente lo que hay que poder ver.
- `result_reference`: que objeto quedo persistido.
- `requires_notification` / `notified`: si al aplicar se le avisa al cliente. Un cambio de
  estado puede disparar un WhatsApp, y eso no se puede deshacer: por eso queda anotado antes
  de aplicar, no despues.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0021"
down_revision = "20261003_0020"
branch_labels = None
depends_on = None

PENDIENTE = "pendiente"
APLICADA = "aplicada"
RECHAZADA = "rechazada"
FALLIDA = "fallida"


def upgrade():
    op.create_table(
        "ai_action_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False),
        # Que herramienta de escritura se quiere ejecutar: crear_cliente, agregar_repuesto, ...
        sa.Column("tool", sa.String(60), nullable=False),
        # pendiente | aplicada | rechazada | fallida
        sa.Column("status", sa.String(20), nullable=False, server_default=PENDIENTE),
        # Quien estaba chateando cuando el modelo propuso. La propuesta se hace en su nombre.
        sa.Column("proposed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("proposed_arguments", sa.Text(), nullable=False),
        # Lo que confirmo la persona. NULL mientras nobody confirmo.
        sa.Column("confirmed_arguments", sa.Text(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        # Que se persistio: {"tipo": "cliente", "id": 123}
        sa.Column("result_reference", sa.Text(), nullable=True),
        sa.Column("result_error", sa.String(500), nullable=True),
        # Riesgo de la accion, segun la herramienta y sus argumentos: ninguno | financiero |
        # comunicacion. Se calcula al proponer, no al aplicar, para que la persona lo vea
        # antes de confirmar y no despues.
        sa.Column("risk", sa.String(20), nullable=False, server_default="ninguno"),
        # Si al aplicar se le avisa al cliente. Un WhatsApp enviado no se puede deshacer.
        sa.Column("requires_notification", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )
    op.create_index("ix_ai_action_proposals_company_id", "ai_action_proposals", ["company_id"])
    # El listado de la pantalla es "las pendientes de esta empresa, mas recientes primero".
    op.create_index("ix_ai_action_proposals_company_status", "ai_action_proposals",
                    ["company_id", "status"])
    op.create_index("ix_ai_action_proposals_created_at", "ai_action_proposals", ["created_at"])


def downgrade():
    op.drop_table("ai_action_proposals")
