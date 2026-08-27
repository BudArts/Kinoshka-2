from sqlalchemy import create_engine

engine = create_engine("sqllite:///database.db", echo=True)
