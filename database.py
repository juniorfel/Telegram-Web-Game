import os
import random
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///idle_war.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Player(Base):
    __tablename__ = "players"
    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(50), nullable=True)
    name = Column(String(15))
    class_name = Column(String(20))
    
    # Progresso
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    gold = Column(Integer, default=1000)
    gems = Column(Integer, default=0)
    current_phase_id = Column(Integer, default=1)
    
    # Atributos de Batalha
    health = Column(Integer)
    max_health = Column(Integer)
    strength = Column(Integer)
    intelligence = Column(Integer)
    defense = Column(Integer)
    speed = Column(Integer, default=5)
    crit_chance = Column(Integer, default=5)
    stamina = Column(Integer, default=5)
    max_stamina = Column(Integer, default=5)
    
    # Social
    pvp_rating = Column(Integer, default=1000)
    guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=True)
    
    # --- NOVO: SISTEMA DE FAZENDA ---
    farm_level = Column(Integer, default=1)      # Nível dos Campos (Produção)
    barn_level = Column(Integer, default=1)      # Nível do Celeiro (Armazenamento)
    last_farm_harvest = Column(DateTime, default=datetime.now) # Última colheita

    # Timestamps
    last_daily_claim = Column(DateTime, default=datetime.min)
    last_stamina_gain = Column(DateTime, default=datetime.min)

class Guild(Base):
    __tablename__ = "guilds"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True)
    telegram_link = Column(String(100)) # Link do Grupo
    leader_id = Column(BigInteger)
    total_rating = Column(Integer, default=0)
    member_count = Column(Integer, default=1) # Contador simples
    created_at = Column(DateTime, default=datetime.now)

def seed_bots(db):
    if db.query(Player).count() > 10: return
    print("Criando bots...")
    prefixes = ["Dark", "Light", "Shadow", "Iron", "Gold", "Fire", "Ice", "Storm", "Elite", "Pro"]
    suffixes = ["Slayer", "King", "Wolf", "Bear", "Hawk", "Lord", "Mage", "Knight", "Br", "X"]
    classes = ["Guerreiro", "Mago", "Arqueiro", "Paladino", "Ogro", "Necromante", "Assassino", "Feiticeiro"]
    bots = []
    for i in range(200):
        name = f"{random.choice(prefixes)}{random.choice(suffixes)}{random.randint(1, 99)}"[:15]
        char_class = random.choice(classes)
        lvl = random.randint(1, 50)
        bot = Player(
            id=100000 + i, username=f"bot_{i}", name=name, class_name=char_class,
            level=lvl, xp=0, gold=random.randint(100, 50000), gems=random.randint(0, 100),
            pvp_rating=1000 + (lvl * 10) + random.randint(-50, 50),
            health=100, max_health=100, strength=10, intelligence=10, defense=10,
            speed=5, crit_chance=5
        )
        bots.append(bot)
    db.add_all(bots)
    db.commit()

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_bots(db)
    db.close()
