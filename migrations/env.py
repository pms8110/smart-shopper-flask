import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# <<< تغییر جدید: وارد کردن اپلیکیشن و مدل‌های دیتابیس شما >>>
# این خط به Alembic می‌گوید که مدل‌های شما کجا تعریف شده‌اند.
from app import app, db

# این یک شیء پیکربندی Alembic است که به مقادیر فایل .ini دسترسی می‌دهد.
config = context.config

# فایل پیکربندی پایتون برای لاگینگ را تفسیر می‌کند.
# این خط اساساً تنظیمات لاگینگ را انجام می‌دهد.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# <<< تغییر جدید: تنظیم صریح target_metadata >>>
# این مهم‌ترین خط است. ما به Alembic می‌گوییم که برای ساخت دیتابیس
# باید از متادیتای شیء `db` که در `app.py` ساختیم، استفاده کند.
target_metadata = db.metadata

# دیگر مقادیر از پیکربندی، در صورت وجود،
# می‌توانند در اینجا تنظیم شوند.

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = app.config['SQLALCHEMY_DATABASE_URI']
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # <<< تغییر جدید: افزودن این خط برای پشتیبانی از SQLite >>>
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # <<< تغییر جدید: استفاده از پیکربندی اپلیکیشن شما >>>
    connectable = db.engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            # <<< تغییر جدید: افزودن این خط برای پشتیبانی از SQLite >>>
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
