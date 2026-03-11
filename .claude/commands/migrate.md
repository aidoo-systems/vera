Create and apply an Alembic database migration.

1. If `$ARGUMENTS` is provided, use it as the migration message. Otherwise, ask the user for a migration description.
2. Generate the migration: `cd backend && alembic revision --autogenerate -m "<message>"`
3. Show the generated migration file for review
4. Ask the user to confirm before applying
5. Apply: `alembic upgrade head`
6. Report success and the new migration version
