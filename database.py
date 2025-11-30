from sqlalchemy import create_engine, Column, Integer, String, BigInteger, Boolean, DateTime, func, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# Configuração do Banco de Dados
# ATENÇÃO: Substitua a string de conexão abaixo pela sua real string do PostgreSQL
# Exemplo: "postgresql://user:password@host:port/dbname"
DATABASE_URL = "sqlite:///idle_war.db" # Usando SQLite para testes locais, mas deve ser PostgreSQL no Render

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Modelos de Dados (Baseados no Esquema PostgreSQL)

class Player(Base):
    __tablename__ = "players"

    id = Column(BigInteger, primary_key=True, index=True) # ID do usuário do Telegram
    username = Column(String(50))
    name = Column(String(100))
    class_name = Column(String(20))
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    gold = Column(Integer, default=0)
    health = Column(Integer)
    max_health = Column(Integer)
    strength = Column(Integer)
    intelligence = Column(Integer)
    defense = Column(Integer)
    last_daily_claim = Column(DateTime, default=datetime.min)
    pvp_rating = Column(Integer, default=1000)
    current_phase_id = Column(Integer, default=1)

    def __init__(self, user_id, username, name, class_name, health, max_health, strength, intelligence, defense):
        self.id = user_id
        self.username = username
        self.name = name
        self.class_name = class_name
        self.health = health
        self.max_health = max_health
        self.strength = strength
        self.intelligence = intelligence
        self.defense = defense
        self.last_daily_claim = datetime.min # Garante que o primeiro daily claim seja possível

    def __repr__(self):
        return f"<Player(id={self.id}, name='{self.name}', level={self.level})>"

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(BigInteger) # Chave Estrangeira (simplificada)
    item_name = Column(String(50))
    quantity = Column(Integer, default=1)
    is_equipped = Column(Boolean, default=False)
    bonus_strength = Column(Integer, default=0)
    bonus_defense = Column(Integer, default=0)

class Monster(Base):
    __tablename__ = "monsters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50))
    phase_level = Column(Integer)
    health = Column(Integer)
    attack = Column(Integer)
    defense = Column(Integer)
    xp_reward = Column(Integer)
    gold_reward = Column(Integer)

# Cria as tabelas no banco de dados (se não existirem)
def init_db():
    Base.metadata.create_all(bind=engine)

# Função para obter a sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    # Exemplo de inicialização e inserção de dados
    init_db()
    print("Banco de dados inicializado com sucesso.")

    # Exemplo de inserção de um monstro inicial
    db = SessionLocal()
    if db.query(Monster).count() == 0:
        goblin = Monster(
            name="Goblin Iniciante",
            phase_level=1,
            health=20,
            attack=5,
            defense=2,
            xp_reward=10,
            gold_reward=5
        )
        db.add(goblin)
        db.commit()
        print("Monstro inicial 'Goblin Iniciante' adicionado.")
    db.close()
