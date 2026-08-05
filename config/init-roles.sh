#!/bin/bash
set -e

# Подключаемся к базе данных под суперпользователем и настраиваем ограниченную роль для приложения
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_APP_USER') THEN
            CREATE ROLE $DB_APP_USER WITH LOGIN PASSWORD '$DB_APP_PASSWORD';
        END IF;
    END
    \$\$;

    -- Даем ограниченному пользователю права на использование схемы public
    GRANT USAGE ON SCHEMA public TO $DB_APP_USER;

    -- Даем права на выполнение DML (SELECT, INSERT, UPDATE, DELETE) на все существующие таблицы и последовательности
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $DB_APP_USER;
    GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO $DB_APP_USER;

    -- Настраиваем права по умолчанию: все новые таблицы, создаваемые администратором схемы,
    -- будут автоматически доступны приложению только для DML операций
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $DB_APP_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO $DB_APP_USER;
EOSQL
