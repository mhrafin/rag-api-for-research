from sqlalchemy.orm import DeclarativeBase


# This is how its done, https://docs.sqlalchemy.org/en/20/orm/declarative_styles.html
class Base(DeclarativeBase):
    pass
