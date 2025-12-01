import random
from datetime import datetime
from database import SessionLocal, Player
from config import ADMIN_ID

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
        player.health = player.max_health 
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

def apply_passive_healing(player, db):
    player.last_stamina_gain = datetime.now()
    return 0

# --- ESTATÍSTICAS TOTAIS (COM BÔNUS DE CARGO) ---
def get_total_stats(player):
    stats = {
        'str': player.strength, 'int': player.intelligence,
        'def': player.defense, 'spd': player.speed, 'hp': player.max_health
    }
    multiplier = 1.0
    if player.guild_id and player.guild_role:
        if player.guild_role == 'lider': multiplier = 1.10    # +10%
        elif player.guild_role == 'coolider': multiplier = 1.05 # +5%
        elif player.guild_role == 'anciao': multiplier = 1.02   # +2%
    
    final_stats = {k: int(v * multiplier) for k, v in stats.items()}
    final_stats['bonus_desc'] = f"+{int((multiplier-1)*100)}%" if multiplier > 1 else ""
    return final_stats

# --- SIMULAÇÃO PVP (COM STATS TOTAIS) ---
def simulate_pvp_battle(attacker, defender):
    s_atk = get_total_stats(attacker)
    s_def = get_total_stats(defender)
    
    hp_atk = s_atk['hp']
    hp_def = s_def['hp']
    atk_turn = s_atk['spd'] >= s_def['spd']
    
    for _ in range(20): # Max 20 turnos
        if hp_atk <= 0 or hp_def <= 0: break
        
        act = s_atk if atk_turn else s_def
        pas = s_def if atk_turn else s_atk
        act_obj = attacker if atk_turn else defender 
        
        if random.randint(1, 100) <= max(0, (pas['spd'] - act['spd']) * 2): # Dodge
            atk_turn = not atk_turn; continue

        dmg = (act['str'] * 2) + act['int']
        if random.randint(1, 100) <= act_obj.crit_chance: dmg *= 2
        
        reduction = pas['def'] / (pas['def'] + 100)
        dmg_final = int(dmg * (1 - reduction))
        
        if atk_turn: hp_def -= dmg_final
        else: hp_atk -= dmg_final
        atk_turn = not atk_turn

    return attacker if hp_atk > 0 else defender

# --- SISTEMA DE ERAS E NÍVEIS ---
def get_guild_level_data(level):
    eras = ["Idade da Pedra", "Idade da Madeira", "Idade do Bronze", 
            "Idade do Ferro", "Idade do Aço", "Era Feudal", 
            "Era Imperial", "Era Mística", "Era Dracônica", "Era Divina"]
    
    if level >= 30: return "Era Divina III", 0
    
    era_index = (level - 1) // 3
    era_name = eras[min(era_index, 9)]
    roman = "I" * ((level - 1) % 3 + 1)
    
    return f"{era_name} {roman}", int(5000 * (level ** 1.5))

def check_guild_level_up(guild):
    leveled_up = False
    while True:
        if guild.level >= 30: break
        _, xp_needed = get_guild_level_data(guild.level)
        if guild.xp >= xp_needed:
            guild.xp -= xp_needed
            guild.level += 1
            leveled_up = True
        else: break
    return leveled_up

def calculate_daily_bonus(player, guild=None):
    gold, xp, gems, bonus_msg = 1000, 1000, 0, ""
    if guild:
        multiplier = 1 + (guild.level * 0.02)
        gold = int(gold * multiplier)
        xp = int(xp * multiplier)
        if guild.level >= 10:
            gems = 2 + (guild.level - 10)
            bonus_msg = f"\n💎 **Bônus de Clã (Nvl {guild.level}):** +{gems} Gemas!"
        else: bonus_msg = f"\n⚠️ _Gemas de Clã desbloqueiam no Nível 10!_"
        bonus_msg = f"\n🛡️ **Bônus de Clã:** +{int((multiplier-1)*100)}% Ouro/XP" + bonus_msg
    return gold, xp, gems, bonus_msg
