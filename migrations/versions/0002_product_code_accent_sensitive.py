"""products.code: compare accents (utf8mb4_0900_as_ci)

The MySQL 8 default, utf8mb4_0900_ai_ci, ignores accents, so CAFE-1 and CAFÉ-1 counted as the
same code in the database but as different codes in Python. With as_ci, case is still ignored
(PRD-1 = prd-1) but accents count, which matches the app's own checks. The unique index on
code stays; MySQL rebuilds it with the new collation.

Revision ID: 7d2e9a41c0b3
Revises: 4c4b47024019
Create Date: 2026-11-08 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7d2e9a41c0b3'
down_revision = '4c4b47024019'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column(
            'code',
            existing_type=sa.String(length=50),
            type_=sa.String(length=50, collation='utf8mb4_0900_as_ci'),
            existing_nullable=False,
        )


def downgrade():
    # Fails if two codes differ only by accents (CAFE-1 and CAFÉ-1): the unique index would
    # see them as the same again. Rename one of them first.
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column(
            'code',
            existing_type=sa.String(length=50, collation='utf8mb4_0900_as_ci'),
            type_=sa.String(length=50, collation='utf8mb4_0900_ai_ci'),
            existing_nullable=False,
        )
