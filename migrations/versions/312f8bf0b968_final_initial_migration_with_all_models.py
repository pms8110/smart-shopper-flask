"""Final initial migration with all models

Revision ID: 312f8bf0b968
Revises: 
Create Date: 2025-07-14 20:54:08.454111

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '312f8bf0b968'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('card_holder_name', sa.String(length=200), nullable=True),
    sa.Column('encrypted_card_number', sa.String(length=200), nullable=True),
    sa.Column('theme', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('dang_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('favorite_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('content', sa.String(length=200), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('shopping_lists',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('dang_event_participants',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('dang_event_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['dang_event_id'], ['dang_events.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'dang_event_id')
    )
    op.create_table('expenses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('payer_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['dang_events.id'], ),
    sa.ForeignKeyConstraint(['payer_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('content', sa.String(length=200), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=True),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('list_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['list_id'], ['shopping_lists.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('list_user_association',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('shopping_list_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['shopping_list_id'], ['shopping_lists.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'shopping_list_id')
    )
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('payer_id', sa.Integer(), nullable=False),
    sa.Column('recipient_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('is_approved', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['dang_events.id'], ),
    sa.ForeignKeyConstraint(['payer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('payments')
    op.drop_table('list_user_association')
    op.drop_table('items')
    op.drop_table('expenses')
    op.drop_table('dang_event_participants')
    op.drop_table('shopping_lists')
    op.drop_table('favorite_items')
    op.drop_table('dang_events')
    op.drop_table('users')
    # ### end Alembic commands ###
