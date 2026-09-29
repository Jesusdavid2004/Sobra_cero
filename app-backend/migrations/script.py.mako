"""${message}"""
from alembic import op
import sqlalchemy as sa
${upgrades if upgrades else ""}

def upgrade():
    pass

def downgrade():
    pass
