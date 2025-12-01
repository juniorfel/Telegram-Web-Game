# utils.py
import random
from datetime import datetime
from database import SessionLocal, Player
from config import ADMIN_ID, HEAL_RATE_PER_HOUR

def get_db():
    return SessionLocal()

def get_player(user_id, db):
    return db.query(Player).filter(Player.id == user_id).first()

def format_number(num):
    return str(int(num)) if num else "0"

def is_admin(user_id, db=None):
    if user_id == ADMIN_ID: return True
    if db:
        p = get_player(user_id, db)
        if p and p.is_admin: return True
    return False

def check_level_up(player):
    leveled_up = False
    if not player.xp: player.xp = 0
    if not player.level: player.level = 1
    while player.xp >= player.level * 100:
        player.xp -= player.level * 100
        player.level += 1
        player.max_health += 5
        player.health = player.max_health # Mantém sincronizado
        player.strength += 1
        player.defense += 1
        leveled_up = True
    return leveled_up

def generate_monster(phase_id):
    mult = 1.1 ** (phase_id - 1)
    is_boss = (phase_id % 10 == 0)
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    gold = 1000 * (2 ** ((phase_id-1)//10)) if is_boss else 100 * (2 ** ((phase_id-1)//10))
    xp = 50 * phase_id
    return {"name": name, "hp": int(30*mult), "atk": int(5*mult), "def": int(2*mult), "spd": int(4*mult), "gold": gold, "xp": xp, "is_boss": is_boss}

def get_construction_cost(level, initial_cost=1000):
    return int(initial_cost * (1.5 ** level))

def apply_passive_healing(player, db):
    # Função mantida apenas para restaurar Stamina se necessário futuramente
    # Como o HP não gasta, ela apenas atualiza o timestamp
    now = datetime.now()
    if not player.last_stamina_gain: 
        player.last_stamina_gain = now
    player.last_stamina_gain = now 
    return 0

def simulate_pvp_battle(attacker, defender):
    """
    Simula batalha sem causar dano permanente ao banco de dados.
    """
    # Variáveis Temporárias para a Simulação
    hp_atk = attacker.max_health # Usa Max Health sempre
    hp_def = defender.max_health
    
    atk_turn = attacker.speed >= defender.speed
    max_turns = 20
    
    for _ in range(max_turns):
        if hp_atk <= 0 or hp_def <= 0: break
        
        act = attacker if atk_turn else defender
        pas = defender if atk_turn else attacker
        
        # Lógica de Combate (Esquiva/Crit/Defesa)
        # Nota: Usamos pas.speed/act.strength direto dos objetos, pois eles não mudam na luta
        
        dodge = max(0, (pas.speed - act.speed) * 2)
        if random.randint(1, 100) <= dodge:
            atk_turn = not atk_turn; continue

        dmg = (act.strength * 2) + act.intelligence
        if random.randint(1, 100) <= act.crit_chance: dmg *= 2
            
        reduction = pas.defense / (pas.defense + 100)
        dmg_final = int(dmg * (1 - reduction))
        
        # Aplica dano nas variáveis LOCAIS (não no banco)
        if pas.id == attacker.id: hp_atk -= dmg_final
        else: hp_def -= dmg_final
        
        atk_turn = not atk_turn

    # Retorna o vencedor baseado no HP restante da simulação
    return attacker if hp_atk > 0 else defender
