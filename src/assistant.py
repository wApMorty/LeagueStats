from typing import List, Dict, Optional
import sys
import locale
from .constants import CHAMPIONS_LIST, CHAMPION_POOL, TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST, SOLOQ_POOL, ROLE_POOLS, EXTENDED_POOLS
from .db import Database
from .config import config

def safe_print(text: str) -> None:
    """Print text with emoji fallback for Windows terminals that don't support UTF-8."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: replace emojis with text equivalents
        fallback_text = text
        emoji_map = {
            '✅': 'OK', '❌': 'ERROR', '⚠️': 'WARNING', '🎯': 'TARGET',
            '📊': 'STATS', '🔸': '-', '🟢': 'GREEN', '🟡': 'YELLOW',
            '🟠': 'ORANGE', '🔴': 'RED', '💡': 'TIPS', '📈': 'TREND',
            '🛡️': 'SHIELD', '🥇': '1st', '🥈': '2nd', '🥉': '3rd',
            '🎮': 'GAME', '➖': '-', '─': '-', '═': '=', '•': '*', '→': '>',
            '⚔️': '[SWORD]', '💥': '[BOOM]', '≥': '>=', '⭐': '*'
        }
        for emoji, replacement in emoji_map.items():
            fallback_text = fallback_text.replace(emoji, replacement)
        print(fallback_text)

class Assistant:
    def __init__(self, verbose: bool = False) -> None:
        self.MIN_GAMES = config.MIN_GAMES_THRESHOLD
        self.db = Database(config.DATABASE_PATH)
        self.db.connect()
        self.verbose = verbose
    
    def close(self) -> None:
        self.db.close()
    
    def select_champion_pool(self) -> List[str]:
        """Interactive pool selection for the user."""
        safe_print("🎯 SELECT YOUR CHAMPION POOL:")
        print("Available pools:")
        print("  1. top     - Top lane champions")
        print("  2. support - Support champions") 
        print("  3. all     - Combined pool (top + support)")
        print()
        
        while True:
            try:
                choice = input("Which pool do you want to use? (top/support/all): ").lower().strip()
                
                if choice in ROLE_POOLS:
                    selected_pool = ROLE_POOLS[choice]
                    safe_print(f"✅ Selected pool: {choice.upper()}")
                    print(f"Champions: {', '.join(selected_pool)}")
                    print()
                    return selected_pool
                else:
                    print("❌ Invalid choice. Please enter: top, support, or all")
                    
            except (EOFError, KeyboardInterrupt):
                print("\nUsing default pool (top)")
                return ROLE_POOLS["top"]

    def select_extended_champion_pool(self) -> List[str]:
        """Interactive extended pool selection for Team Builder analysis."""
        safe_print("🎯 SELECT CHAMPION POOL FOR ANALYSIS:")
        print("Extended pools for comprehensive analysis:")
        print("  1. top        - Extended top lane pool (~24 champions)")
        print("  2. support    - Extended support pool (~26 champions)")  
        print("  3. jungle     - Extended jungle pool (~22 champions)")
        print("  4. mid        - Extended mid lane pool (~29 champions)")
        print("  5. adc        - Extended ADC pool (~21 champions)")
        print("  6. multi-role - Top + Support combined (~50 champions)")
        print("  7. all-roles  - All roles combined (~120+ champions)")
        print()
        
        pool_options = {
            "1": "top", "top": "top",
            "2": "support", "support": "support", "supp": "support",
            "3": "jungle", "jungle": "jungle", "jgl": "jungle",
            "4": "mid", "mid": "mid", "middle": "mid",
            "5": "adc", "adc": "adc", "bot": "adc",
            "6": "multi-role", "multi": "multi-role", "multi-role": "multi-role",
            "7": "all-roles", "all": "all-roles", "all-roles": "all-roles"
        }
        
        while True:
            try:
                choice = input("Which extended pool? (1-7 or role name): ").lower().strip()
                
                if choice in pool_options:
                    pool_key = pool_options[choice]
                    selected_pool = EXTENDED_POOLS[pool_key]
                    safe_print(f"✅ Selected extended pool: {pool_key.upper()}")
                    print(f"Pool size: {len(selected_pool)} champions")
                    print(f"First few: {', '.join(selected_pool[:5])}, ...")
                    print()
                    return selected_pool
                else:
                    print("❌ Invalid choice. Use 1-7 or role names (top, support, jungle, mid, adc, multi-role, all-roles)")
                    
            except (EOFError, KeyboardInterrupt):
                print("\nUsing default extended pool (top)")
                return EXTENDED_POOLS["top"]

    def _filter_valid_matchups(self, matchups: List[tuple]) -> List[tuple]:
        """Filter matchups with sufficient pick rate and games data."""
        return [m for m in matchups if m[4] >= config.MIN_PICKRATE and m[5] >= config.MIN_MATCHUP_GAMES]

    def avg_delta1(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta1 from valid matchups."""
        valid_matchups = self._filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m[4] for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m[2] * m[4] for m in valid_matchups) / total_weight

    def avg_delta2(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta2 from valid matchups."""
        valid_matchups = self._filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m[4] for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m[3] * m[4] for m in valid_matchups) / total_weight
    
    def avg_winrate(self, matchups: List[tuple]) -> float:
        """Calculate weighted average winrate from valid matchups."""
        valid_matchups = self._filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m[4] for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m[1] * m[4] for m in valid_matchups) / total_weight

    def score_against_team(self, matchups: List[tuple], team: List[str], champion_name: str = None) -> float:
        """
        Calculate advantage against a team composition using base winrate + delta2.
        
        Args:
            matchups: List of matchup data tuples
            team: Enemy team composition
            champion_name: Name of our champion (for accurate base winrate calculation)
        
        Returns:
            float: Expected advantage in percentage points (positive = favorable)
        """
        if not champion_name:
            # Can't calculate accurately without champion name, return 0
            if self.verbose:
                print("[WARNING] score_against_team called without champion_name, returning neutral advantage")
            return 0.0
        
        # Use new logistic transformation for delta2 to advantage conversion
        if not team:
            # Pure blind pick scenario
            avg_delta2 = self.avg_delta2(matchups)
            return self._delta2_to_win_advantage(avg_delta2, champion_name)
        
        total_delta2 = 0
        matchup_count = 0
        remaining_matchups = matchups.copy()
        
        # Calculate delta2 for known matchups
        for enemy in team:
            for i, matchup in enumerate(remaining_matchups):
                if matchup[0].lower() == enemy.lower():
                    delta2 = matchup[3]
                    total_delta2 += delta2
                    matchup_count += 1
                    remaining_matchups.pop(i)
                    break
        
        # Calculate delta2 for unknown matchups (blind picks)
        blind_picks = 5 - len(team)
        if blind_picks > 0:
            avg_delta2 = self.avg_delta2(remaining_matchups)
            total_delta2 += blind_picks * avg_delta2
            matchup_count += blind_picks
        
        # Convert average delta2 to advantage using logistic transformation
        if matchup_count == 0:
            return 0.0  # No data available
        else:
            avg_delta2 = total_delta2 / matchup_count
            return self._delta2_to_win_advantage(avg_delta2, champion_name)
    
    def _delta2_to_win_advantage(self, delta2: float, champion_name: str) -> float:
        """
        Convert delta2 value to win advantage using logistic transformation.
        
        Uses mathematical model from CLAUDE.md:
        - Logistic scaling for realistic bounds and diminishing returns
        - log_odds = 0.12 * delta2 (~1.2% per delta2 unit)
        - advantage = (win_probability - 0.5) * 100
        
        Args:
            delta2: The delta2 value from matchup data
            champion_name: Champion name (kept for interface compatibility)
            
        Returns:
            float: Win advantage percentage (positive = our team favored)
        """
        import math
        
        # Logistic transformation for realistic bounds
        log_odds = 0.12 * delta2  # ~1.2% per delta2 unit
        win_probability = 1 / (1 + math.exp(-log_odds))
        advantage = (win_probability - 0.5) * 100  # Percentage points from 50% baseline
        
        # Apply conservative bounds (-10% to +10%)
        return max(-10.0, min(10.0, advantage))

    def tierlist_delta1(self, champion_list: List[str]) -> List[tuple]:
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.MIN_GAMES:
                continue  # Skip this champion but continue processing others
            score = self.avg_delta1(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def tierlist_delta2(self, champion_list) -> List[tuple]:
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.MIN_GAMES:
                continue  # Skip this champion but continue processing others
            score = self.avg_delta2(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def tierlist_lane(self, lane: str) -> List[tuple]:
        champion_list = ""
        if lane == "top":
            champion_list = TOP_LIST
        elif lane == "jungle":
            champion_list = JUNGLE_LIST
        elif lane == "mid":
            champion_list = MID_LIST
        elif lane == "adc":
            champion_list = ADC_LIST
        elif lane == "support":
            champion_list = SUPPORT_LIST
        else:
            print("Invalid lane specified.")
            return []        
        return self.tierlist_delta2(champion_list)

    def draft(self, nb_results: int) -> None:
        scores = []
        enemy_team = []
        _results = nb_results
        
        enemy = input("Champion 1 :")
        while(enemy != "" and len(enemy_team)<4):
            enemy_team.append(enemy)
            enemy = input(f"Champion {len(enemy_team) + 1} :")

        for champion in CHAMPION_POOL:
            if champion not in enemy_team:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if sum(m[5] for m in matchups) < 10000:
                    break
                score = self.score_against_team(matchups, enemy_team, champion_name=champion)
                scores.append((str(champion), score))
                scores.sort(key=lambda x: -x[1])

        for index in range(min(_results, len(CHAMPION_POOL))):
            print(scores[index])
        while (input("Want more ?") == "y"):
            _results += nb_results
            for index in range(_results):
                print(scores[index])

    def _calculate_and_display_recommendations(self, enemy_team: List[str], ally_team: List[str], nb_results: int, champion_pool: List[str] = None, banned_champions: List[str] = None) -> List[tuple]:
        """
        Calculate champion recommendations and display top results.

        Args:
            enemy_team: List of enemy champions
            ally_team: List of ally champions
            nb_results: Number of results to display
            champion_pool: Pool to select from (defaults to SOLOQ_POOL)
            banned_champions: List of banned champions to exclude

        Returns:
            List of (champion, advantage) tuples, sorted by score
        """
        if champion_pool is None:
            champion_pool = SOLOQ_POOL
        if banned_champions is None:
            banned_champions = []

        scores = []
        skipped_low_data = 0

        for champion in champion_pool:
            # Skip if already picked or banned
            if champion in enemy_team or champion in ally_team or champion in banned_champions:
                continue

            matchups = self.db.get_champion_matchups_by_name(champion)
            total_games = sum(m[5] for m in matchups)

            if total_games < config.MIN_GAMES_COMPETITIVE:
                skipped_low_data += 1
                continue

            score = self.score_against_team(matchups, enemy_team, champion_name=champion)
            scores.append((str(champion), score))

        scores.sort(key=lambda x: -x[1])

        # Display formatted results
        if scores:
            rank_emojis = ["🥇", "🥈", "🥉"]
            for index in range(min(nb_results, len(scores))):
                champion, advantage = scores[index]
                rank = rank_emojis[index] if index < 3 else f"  {index+1}."
                print(f"{rank} {champion:<15} | {advantage:+6.2f}% advantage")
        else:
            print("  ⚠️ No recommendations available")
            if skipped_low_data > 0:
                print(f"     ({skipped_low_data} champions skipped - insufficient data)")

        return scores
    
    def validate_champion_name(self, name: str) -> Optional[str]:
        """
        Validate and normalize champion name.

        Args:
            name: Champion name to validate

        Returns:
            Normalized champion name if valid, None otherwise
        """
        if not name:
            return None

        from .constants import CHAMPIONS_LIST

        # Normalize input
        normalized = name.strip()

        # Try exact match (case-insensitive)
        for champion in CHAMPIONS_LIST:
            if champion.lower() == normalized.lower():
                return champion

        # Try fuzzy match (starts with)
        suggestions = [c for c in CHAMPIONS_LIST if c.lower().startswith(normalized.lower())]

        if len(suggestions) == 1:
            # Single match - auto-complete
            return suggestions[0]
        elif len(suggestions) > 1:
            # Multiple matches - show suggestions
            print(f"  ⚠️ Ambiguous name. Did you mean: {', '.join(suggestions[:5])}?")
            return None
        else:
            # No matches - try contains
            contains_matches = [c for c in CHAMPIONS_LIST if normalized.lower() in c.lower()]
            if contains_matches:
                print(f"  ⚠️ Champion not found. Similar: {', '.join(contains_matches[:5])}")
            else:
                print(f"  ❌ Champion '{name}' not found")
            return None

    def _get_champion_input(self, team_name: str, champion_number: int) -> str:
        """Get champion input from user with consistent formatting."""
        return input(f"{team_name} - Champion {champion_number}: ")
    
    def _draft_red_side(self, enemy_team: List[str], ally_team: List[str], nb_results: int) -> None:
        """Handle red side draft sequence."""
        # Pick 1
        enemy_team.append(self._get_champion_input("Equipe 1", 1))
        
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 2", 1))
        ally_team.append(self._get_champion_input("Equipe 2", 2))
        
        # Pick 2-3
        enemy_team.append(self._get_champion_input("Equipe 1", 2))
        enemy_team.append(self._get_champion_input("Equipe 1", 3))
        
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 2", 3))
        ally_team.append(self._get_champion_input("Equipe 2", 4))
        
        # Pick 4-5
        enemy_team.append(self._get_champion_input("Equipe 1", 4))
        enemy_team.append(self._get_champion_input("Equipe 1", 5))
        
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 2", 5))
    
    def _draft_blue_side(self, enemy_team: List[str], ally_team: List[str], nb_results: int) -> None:
        """Handle blue side draft sequence."""
        # Initial recommendations
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        
        # Pick 1
        ally_team.append(self._get_champion_input("Equipe 1", 1))
        
        enemy_team.append(self._get_champion_input("Equipe 2", 1))
        enemy_team.append(self._get_champion_input("Equipe 2", 2))
        
        # Pick 2
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 1", 2))
        ally_team.append(self._get_champion_input("Equipe 1", 3))
        
        # Pick 3-4
        enemy_team.append(self._get_champion_input("Equipe 2", 3))
        enemy_team.append(self._get_champion_input("Equipe 2", 4))
        
        # Pick 4
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 1", 4))
        ally_team.append(self._get_champion_input("Equipe 1", 5))
        
        enemy_team.append(self._get_champion_input("Equipe 2", 5))

    def competitive_draft(self, nb_results: int) -> None:
        """Simulate a competitive draft with pick recommendations."""
        enemy_team = []
        ally_team = []
        side = input("Side : ")

        if side.lower() == 'r':
            self._draft_red_side(enemy_team, ally_team, nb_results)
            self.score_teams(enemy_team, ally_team)
        elif side.lower() == 'b':
            self._draft_blue_side(enemy_team, ally_team, nb_results)
            self.score_teams(ally_team, enemy_team)
        else:
            print("Couldn't parse side")

    def blind_pick(self) -> None:
        lst = self.tierlist_delta2()
        _results = 10

        if len(lst)<_results:
            for index in range(len(lst)):
                print(lst[index])
        else:
            for index in range(_results):
                print(lst[index])
            while (input("Want more ?") == "y"):
                _results += 10
                for index in range(_results):
                    print(lst[index])
    
    def _calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """
        Calculate team win probability from individual champion winrates using geometric mean.
        
        Uses probability theory to combine individual winrates:
        - Converts winrates to probabilities (divide by 100)
        - Calculates team probability using geometric mean (multiplicative effects)
        - More mathematically sound than arithmetic averaging
        
        Args:
            individual_winrates: List of actual winrates (e.g. [54.2, 48.5, 52.1])
            
        Returns:
            dict with 'team_winrate', 'individual_winrates'
        """
        import math
        
        if not individual_winrates:
            return {'team_winrate': 50.0, 'individual_winrates': []}
        
        # Clamp individual winrates to realistic bounds
        clamped_winrates = []
        for winrate in individual_winrates:
            clamped_winrate = max(20.0, min(80.0, winrate))
            clamped_winrates.append(clamped_winrate)
        
        # Convert to probabilities and calculate geometric mean
        geometric_mean = 1.0
        for winrate in clamped_winrates:
            probability = winrate / 100.0  # Convert to probability (0.0 to 1.0)
            geometric_mean *= probability
        
        # Take nth root to get geometric mean probability
        geometric_mean = geometric_mean ** (1.0 / len(clamped_winrates))
        
        # Convert back to percentage
        team_winrate = geometric_mean * 100.0
        
        # Apply conservative bounds (extreme team winrates are unrealistic)
        team_winrate = max(25.0, min(75.0, team_winrate))
        
        return {
            'team_winrate': team_winrate,
            'individual_winrates': clamped_winrates
        }

    def score_teams(self, team1: List[str], team2: List[str]) -> None:
        """Statistical team analysis using geometric mean for team winrates."""
        scores1 = []
        for champion in team1:
            advantage = self.score_against_team(self.db.get_champion_matchups_by_name(champion), team2, champion_name=champion)
            scores1.append((champion, advantage))
        
        scores2 = []
        for champion in team2:
            advantage = self.score_against_team(self.db.get_champion_matchups_by_name(champion), team1, champion_name=champion)
            scores2.append((champion, advantage))
        
        # Convert advantages to winrates for geometric mean calculation
        # score_against_team returns advantage in percentage points from 50% baseline
        # So winrate = 50.0 + advantage (e.g., +3.5% advantage = 53.5% winrate)
        winrates1 = [50.0 + advantage for champion, advantage in scores1]
        winrates2 = [50.0 + advantage for champion, advantage in scores2]
        
        team1_stats = self._calculate_team_winrate(winrates1)
        team2_stats = self._calculate_team_winrate(winrates2)
        
        # Normalize team winrates to ensure they sum to 100%
        total_winrate = team1_stats['team_winrate'] + team2_stats['team_winrate']
        if total_winrate > 0:
            team1_normalized = (team1_stats['team_winrate'] / total_winrate) * 100.0
            team2_normalized = (team2_stats['team_winrate'] / total_winrate) * 100.0
        else:
            team1_normalized = team2_normalized = 50.0  # Fallback for edge case
        
        # Update stats with normalized values
        team1_stats['raw_winrate'] = team1_stats['team_winrate']
        team2_stats['raw_winrate'] = team2_stats['team_winrate'] 
        team1_stats['team_winrate'] = team1_normalized
        team2_stats['team_winrate'] = team2_normalized
        
        # Display results
        print("=" * 60)
        safe_print(f"🔵 TEAM 1 ANALYSIS:")
        print("-" * 40)
        for champion, advantage in scores1:
            winrate = 50.0 + advantage
            print(f"{champion:<15} | {advantage:+5.2f}% advantage ({winrate:.1f}% winrate)")

        print("-" * 40)
        safe_print(f"🎯 Team Winrate: {team1_stats['team_winrate']:.1f}% (raw: {team1_stats['raw_winrate']:.1f}%)")

        print("=" * 60)
        safe_print(f"🔴 TEAM 2 ANALYSIS:")
        print("-" * 40)
        for champion, advantage in scores2:
            winrate = 50.0 + advantage
            print(f"{champion:<15} | {advantage:+5.2f}% advantage ({winrate:.1f}% winrate)")
        
        print("-" * 40)
        safe_print(f"🎯 Team Winrate: {team2_stats['team_winrate']:.1f}% (raw: {team2_stats['raw_winrate']:.1f}%)")
        
        # Matchup prediction
        print("=" * 60)
        safe_print(f"📊 MATCHUP PREDICTION:")
        team_diff = team1_stats['team_winrate'] - team2_stats['team_winrate']
        
        print(f"Team 1 vs Team 2: {team1_stats['team_winrate']:.1f}% vs {team2_stats['team_winrate']:.1f}%")
        print(f"Expected advantage: {team_diff:+.1f}% for Team 1")
        
        # Confidence level based on magnitude
        if abs(team_diff) >= 10:
            safe_print(f"🟢 Strong advantage predicted")
        elif abs(team_diff) >= 5:
            safe_print(f"🟡 Moderate advantage predicted") 
        elif abs(team_diff) >= 2:
            safe_print(f"🟠 Small advantage predicted")
        else:
            safe_print(f"⚪ Very close matchup predicted")
        
        print("=" * 60)
    
    def score_teams_no_input(self) -> None:
        team1 = []
        team2 = []

        for i in range(5):
            team1.append(input(f"Team 1 - Champion {i+1}:"))
        for i in range(5):
            team2.append(input(f"Team 2 - Champion {i+1}:"))
        
        self.score_teams(team1, team2)

    def print_champion_list(self, champion_list: List[tuple]) -> None:
        print("=========================")
        for champion in champion_list:
            print(f"{champion[0]} - {champion[1]}")
        print("=========================")

    def _validate_champion_data(self, champion: str) -> tuple:
        """
        Validate if a champion has sufficient data in database.
        
        Returns:
            (has_data: bool, matchup_count: int, total_games: int, avg_delta2: float)
        """
        try:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if not matchups:
                return (False, 0, 0, 0.0)
            
            matchup_count = len(matchups)
            total_games = sum(m[5] for m in matchups)  # games are at index 5
            avg_delta2 = self.avg_delta2(matchups)
            
            # Consider champion viable if has enough data
            has_sufficient_data = (
                matchup_count >= 5 and  # At least 5 matchups
                total_games >= self.MIN_GAMES  # At least MIN_GAMES total games
            )
            
            return (has_sufficient_data, matchup_count, total_games, avg_delta2)
            
        except Exception as e:
            print(f"Error validating {champion}: {e}")
            return (False, 0, 0, 0.0)

    def _validate_champion_pool(self, champion_pool: List[str]) -> tuple:
        """
        Validate entire champion pool and return viable champions.
        
        Returns:
            (viable_champions: List[str], validation_report: dict)
        """
        viable_champions = []
        validation_report = {}
        
        print("Validating champion pool data...")
        
        for champion in champion_pool:
            has_data, matchups, games, delta2 = self._validate_champion_data(champion)
            
            validation_report[champion] = {
                'has_data': has_data,
                'matchups': matchups,
                'total_games': games,
                'avg_delta2': delta2
            }
            
            if has_data:
                viable_champions.append(champion)
                safe_print(f"  ✅ {champion}: {matchups} matchups, {games} total games, {delta2:.2f} avg delta2")
            else:
                safe_print(f"  ❌ {champion}: Insufficient data ({matchups} matchups, {games} games)")
        
        return viable_champions, validation_report

    def get_ban_recommendations(self, champion_pool: List[str], num_bans: int = 5) -> List[tuple]:
        """
        Get ban recommendations against a specific champion pool using reverse lookup.
        
        For each potential enemy pick, finds your BEST response from your pool.
        Prioritizes banning enemies where even your best response is insufficient.
        
        Args:
            champion_pool: List of champion names in your pool
            num_bans: Number of ban recommendations to return
            
        Returns:
            List of tuples (enemy_name, threat_score, champions_countered)
            Where champions_countered is the number of champions in your pool that have negative delta2 vs this enemy
            Sorted by threat_score (descending)
        """
        # Get all potential enemies from database
        all_potential_enemies = set()
        for our_champion in champion_pool:
            try:
                matchups = self.db.get_champion_matchups_by_name(our_champion)
                for enemy_name, winrate, delta1, delta2, pickrate, games in matchups:
                    if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                        all_potential_enemies.add(enemy_name)
            except Exception as e:
                if self.verbose:
                    print(f"Error getting enemies for {our_champion}: {e}")
                continue
        
        ban_candidates = []
        
        # For each potential enemy, find our best response and count how many it counters
        for enemy_champion in all_potential_enemies:
            best_response_delta2 = -float('inf')
            best_response_champion = None
            enemy_pickrate = 0.0
            matchups_found = 0
            champions_countered = 0  # Count of our champions with negative delta2 vs this enemy
            
            # Check all our champions against this enemy
            for our_champion in champion_pool:
                try:
                    delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)
                    
                    if delta2 is not None:
                        matchups_found += 1
                        
                        # Count champions that are countered (negative delta2)
                        if delta2 < 0:
                            champions_countered += 1
                        
                        # Track the best response we have
                        if delta2 > best_response_delta2:
                            best_response_delta2 = delta2
                            best_response_champion = our_champion
                        
                        # Also get pickrate data for this enemy (approximate from one of our matchups)
                        if enemy_pickrate == 0.0:
                            try:
                                matchups = self.db.get_champion_matchups_by_name(our_champion)
                                for enemy_name, winrate, delta1, d2, pickrate, games in matchups:
                                    if enemy_name == enemy_champion:
                                        enemy_pickrate = pickrate
                                        break
                            except:
                                pass
                                
                except Exception as e:
                    if self.verbose:
                        print(f"Error checking {our_champion} vs {enemy_champion}: {e}")
                    continue
            
            # Skip if no valid matchups found
            if best_response_champion is None or matchups_found == 0:
                continue
            
            # Calculate threat score: Higher score = enemy should be banned
            # Key insight: If even our BEST response has negative delta2, this enemy is very threatening
            base_threat = -best_response_delta2  # Invert: negative delta2 = high threat
            
            # Weight by pickrate and how many champions it counters
            pickrate_weight = max(enemy_pickrate, 1.0)  # At least 1.0 to avoid zero weights
            counter_ratio = champions_countered / len(champion_pool)  # Fraction of our pool this enemy counters
            
            # Combined threat score
            # - Main factor: How bad is our best response? (70%)
            # - Secondary: How popular is this enemy? (20%) 
            # - Tertiary: How many of our champions does it counter? (10%)
            combined_threat = (
                base_threat * 0.7 +
                pickrate_weight * 0.2 +
                counter_ratio * 10.0 * 0.1  # Scale counter ratio to reasonable range
            )
            
            ban_candidates.append((
                enemy_champion,
                combined_threat,
                champions_countered,  # Now correctly shows number of champions countered
                best_response_champion,
                best_response_delta2
            ))
        
        # Sort by combined threat (descending)
        ban_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Return in clean format: (enemy, threat_score, champions_countered)  
        return [(name, threat, countered) for name, threat, countered, _, _ in ban_candidates[:num_bans]]

    def find_optimal_trios_holistic(self, champion_pool: List[str], num_results: int = 5, profile: str = "balanced") -> List[dict]:
        """
        Find optimal 3-champion combinations using holistic evaluation.
        
        Unlike the blind-pick approach, this evaluates all possible trios as complete units.
        
        Args:
            champion_pool: List of champion names to choose from
            num_results: Number of top trios to return
            profile: Scoring profile ("safe", "meta", "aggressive", "balanced")
            
        Returns:
            List of dictionaries with trio information and scores
            
        Algorithm:
        1. Generate all combinations of 3 champions
        2. For each trio, calculate holistic score based on:
           - Coverage: How well they handle all potential enemies
           - Balance: Diversity of matchup profiles (avoid same weaknesses)
           - Consistency: Reliable performance across situations
           - Meta relevance: Performance against popular picks
        """
        import itertools
        
        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")
        
        print(f"Analyzing all trio combinations from pool: {champion_pool}")
        
        # Step 1: Validate champion data availability
        viable_champions, validation_report = self._validate_champion_pool(champion_pool)
        
        if len(viable_champions) < 3:
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")
        
        # Step 2: Generate all combinations of 3 champions
        trio_combinations = list(itertools.combinations(viable_champions, 3))
        print(f"Evaluating {len(trio_combinations)} trio combinations...")
        
        trio_rankings = []
        
        # Set the scoring profile for this analysis
        self.scoring_profile = profile
        if self.verbose:
            print(f"[INFO] Using scoring profile: {profile}")
        
        # Step 3: Evaluate each trio holistically
        for trio in trio_combinations:
            try:
                trio_score = self._evaluate_trio_holistic(trio)
                trio_rankings.append({
                    'trio': trio,
                    'total_score': trio_score['total_score'],
                    'coverage_score': trio_score['coverage_score'],
                    'balance_score': trio_score['balance_score'], 
                    'consistency_score': trio_score['consistency_score'],
                    'meta_score': trio_score['meta_score'],
                    'enemy_coverage': trio_score['enemy_coverage']
                })
            except Exception as e:
                if self.verbose:
                    print(f"Error evaluating trio {trio}: {e}")
                continue
        
        if not trio_rankings:
            raise ValueError("No viable trios found after evaluation")
        
        # Step 4: Sort by total score
        trio_rankings.sort(key=lambda x: x['total_score'], reverse=True)
        
        return trio_rankings[:num_results]

    def _evaluate_trio_holistic(self, trio: tuple) -> dict:
        """
        Evaluate a trio of champions using holistic scoring with reverse lookup.
        
        Uses efficient reverse lookup to avoid duplicate matchups and improve performance.
        
        Returns dict with individual scores and total score.
        """
        champion1, champion2, champion3 = trio
        trio_list = [champion1, champion2, champion3]
        
        # Use reverse lookup to build enemy coverage efficiently
        enemy_coverage = {}  # enemy_name -> (best_delta2, champion_handling_it)
        
        for enemy_champion in CHAMPIONS_LIST:
            best_delta2 = -float('inf')
            best_counter = None
            
            # For this enemy, check which champion in our trio counters it best
            for our_champion in trio_list:
                try:
                    delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)
                    
                    if delta2 is not None and delta2 > best_delta2:
                        best_delta2 = delta2
                        best_counter = our_champion
                        
                except Exception as e:
                    if self.verbose:
                        print(f"Error getting matchup {our_champion} vs {enemy_champion}: {e}")
                    continue
            
            # If we found a valid matchup, record it
            if best_counter is not None and best_delta2 != -float('inf'):
                enemy_coverage[enemy_champion] = (best_delta2, best_counter)
        
        all_enemies = set(enemy_coverage.keys())
        
        # Calculate individual scores using the reverse-lookup data
        coverage_score = self._calculate_coverage_score(enemy_coverage, all_enemies)
        balance_score = self._calculate_balance_score_reverse(trio_list, enemy_coverage)
        consistency_score = self._calculate_consistency_score_reverse(trio_list, enemy_coverage)
        meta_score = self._calculate_meta_score(enemy_coverage)
        
        # Calculate contextual total score using adaptive weights
        total_score, used_weights = self._calculate_contextual_total_score(
            {
                'coverage_score': coverage_score,
                'balance_score': balance_score,
                'consistency_score': consistency_score,
                'meta_score': meta_score
            },
            profile=getattr(self, 'scoring_profile', 'balanced')
        )
        
        return {
            'total_score': total_score,
            'coverage_score': coverage_score,
            'balance_score': balance_score,
            'consistency_score': consistency_score, 
            'meta_score': meta_score,
            'enemy_coverage': enemy_coverage
        }

    def _calculate_coverage_score(self, enemy_coverage: dict, all_enemies: set) -> float:
        """Calculate how well the trio covers all potential enemies."""
        if not all_enemies:
            return 0.0
        
        # Sum of best delta2 scores against all enemies
        total_coverage = sum(max(0, delta2) for delta2, _ in enemy_coverage.values())
        max_possible = len(all_enemies) * 10  # Theoretical max delta2 is around 10
        
        return min(100.0, (total_coverage / max_possible) * 100)

    def _calculate_balance_score_reverse(self, trio_list: List[str], enemy_coverage: dict) -> float:
        """
        Calculate diversity of matchup profiles using reverse lookup data.
        
        Args:
            trio_list: List of champion names in the trio
            enemy_coverage: Dict mapping enemy -> (delta2, best_counter)
            
        Returns:
            Balance score 0-100 (higher = more balanced, fewer shared weaknesses)
        """
        try:
            # For each champion, identify their weaknesses from enemy_coverage
            champion_weaknesses = {champ: set() for champ in trio_list}
            
            for enemy, (best_delta2, best_counter) in enemy_coverage.items():
                # Check each champion individually against this enemy
                for our_champion in trio_list:
                    try:
                        delta2 = self.db.get_matchup_delta2(our_champion, enemy)
                        
                        # If this champion struggles against this enemy (negative delta2)
                        if delta2 is not None and delta2 < -2.0:
                            champion_weaknesses[our_champion].add(enemy)
                            
                    except Exception:
                        continue
            
            # Calculate overlap in weaknesses
            weakness_sets = list(champion_weaknesses.values())
            if len(weakness_sets) < 2:
                return 50.0
            
            # Get union and intersection of all weaknesses
            all_weaknesses = set.union(*weakness_sets) if weakness_sets else set()
            shared_weaknesses = set.intersection(*weakness_sets) if weakness_sets else set()
            
            if len(all_weaknesses) == 0:
                return 100.0  # No weaknesses found
            
            # Calculate balance: fewer shared weaknesses = better balance
            balance_ratio = 1 - (len(shared_weaknesses) / len(all_weaknesses))
            return balance_ratio * 100
            
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Balance score calculation failed: {e}")
            return 50.0  # Neutral score on error

    def _calculate_consistency_score_reverse(self, trio_list: List[str], enemy_coverage: dict) -> float:
        """
        Calculate consistency using reverse lookup data.
        
        Args:
            trio_list: List of champion names in the trio
            enemy_coverage: Dict mapping enemy -> (delta2, best_counter)
            
        Returns:
            Consistency score 0-100 (higher = more consistent performance)
        """
        try:
            all_delta2_scores = []
            
            # Collect all delta2 scores from the coverage data
            for enemy, (delta2, counter) in enemy_coverage.items():
                all_delta2_scores.append(delta2)
            
            if not all_delta2_scores:
                return 0.0
            
            # Calculate consistency metrics
            import statistics
            mean_score = statistics.mean(all_delta2_scores)
            
            if len(all_delta2_scores) > 1:
                variance = statistics.variance(all_delta2_scores)
                # Convert variance to consistency score (lower variance = higher consistency)
                consistency = max(0, 100 - (variance * 5))  # Scale appropriately
            else:
                consistency = 50  # Neutral if only one score
            
            # Factor in average performance
            avg_performance = max(0, mean_score + 5) * 10  # Shift and scale (-5 to +5 -> 0 to 100)
            
            # Weighted combination: 60% consistency, 40% performance
            return (consistency * 0.6 + avg_performance * 0.4)
            
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Consistency score calculation failed: {e}")
            return 50.0

    def _calculate_balance_score(self, trio: tuple, all_matchups: List[List]) -> float:
        """Calculate diversity of matchup profiles to avoid same weaknesses."""
        try:
            # For each champion, get their worst matchups (big threats)
            champion_weaknesses = []
            
            for i, matchups in enumerate(all_matchups):
                weaknesses = []
                for enemy, winrate, delta1, delta2, pickrate, games in matchups:
                    if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                        if delta2 < -2.0:  # Significantly negative matchup
                            weaknesses.append(enemy)
                champion_weaknesses.append(set(weaknesses))
            
            # Calculate overlap in weaknesses (lower overlap = better balance)
            if len(champion_weaknesses) < 2:
                return 50.0
            
            total_weaknesses = len(champion_weaknesses[0] | champion_weaknesses[1] | champion_weaknesses[2])
            shared_weaknesses = len(champion_weaknesses[0] & champion_weaknesses[1] & champion_weaknesses[2])
            
            if total_weaknesses == 0:
                return 100.0
            
            balance_ratio = 1 - (shared_weaknesses / total_weaknesses)
            return balance_ratio * 100
            
        except:
            return 50.0  # Neutral score on error

    def _calculate_consistency_score(self, trio: tuple, all_matchups: List[List]) -> float:
        """Calculate how consistently the trio performs across matchups."""
        try:
            all_scores = []
            
            for matchups in all_matchups:
                for enemy, winrate, delta1, delta2, pickrate, games in matchups:
                    if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                        all_scores.append(delta2)
            
            if not all_scores:
                return 0.0
            
            # Lower variance = more consistent
            import statistics
            mean_score = statistics.mean(all_scores)
            if len(all_scores) > 1:
                variance = statistics.variance(all_scores)
                # Convert variance to consistency score (0-100)
                consistency = max(0, 100 - (variance * 5))  # Scale variance appropriately
            else:
                consistency = 50
            
            # Also factor in average performance
            avg_performance = max(0, mean_score + 5) * 10  # Shift and scale
            
            return (consistency * 0.6 + avg_performance * 0.4)
            
        except:
            return 50.0

    def _calculate_meta_score(self, enemy_coverage: dict) -> float:
        """
        Calculate performance against popular/meta champions.
        
        Uses actual pickrate data to determine meta relevance:
        - Gets pickrate for each enemy champion from database
        - Calculates weighted average of delta2 scores by pickrate
        - Higher pickrate champions have more influence on the score
        
        Returns:
            Score 0-100 representing performance vs meta champions
        """
        try:
            if not enemy_coverage:
                return 50.0  # Neutral if no coverage data
            
            # Get pickrate data for all enemies and calculate weighted score
            weighted_sum = 0.0
            total_weight = 0.0
            
            for enemy, (delta2, _) in enemy_coverage.items():
                try:
                    # Get pickrate for this enemy champion
                    enemy_matchups = self.db.get_champion_matchups_by_name(enemy)
                    if not enemy_matchups:
                        continue
                    
                    # Calculate average pickrate for this champion
                    # Each matchup has: (enemy_id, winrate, delta1, delta2, pickrate, games)
                    pickrates = [matchup[4] for matchup in enemy_matchups if len(matchup) > 4 and matchup[4] > 0]
                    
                    if not pickrates:
                        continue
                    
                    avg_pickrate = sum(pickrates) / len(pickrates)
                    
                    # Weight the delta2 score by pickrate
                    # Higher pickrate = more meta relevant = higher weight
                    weight = avg_pickrate
                    weighted_sum += max(0, delta2) * weight
                    total_weight += weight
                    
                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error processing {enemy} pickrate: {e}")
                    continue
            
            if total_weight == 0:
                return 50.0  # No valid pickrate data
            
            # Calculate weighted average
            weighted_avg = weighted_sum / total_weight
            
            # Scale to 0-100 range
            # delta2 typically ranges from -5 to +5, so we shift and scale
            score = min(100.0, max(0.0, (weighted_avg + 5) * 10))
            
            return score
            
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Meta score calculation failed: {e}")
            return 50.0

    def _calculate_enemy_coverage(self, matchups_list: List[List]) -> Dict[str, tuple]:
        """
        Calculate enemy coverage for a set of champions.
        
        Args:
            matchups_list: List of matchup lists for each champion
            
        Returns:
            Dictionary mapping enemy_name -> (best_delta2, champion_handling_it)
        """
        enemy_coverage = {}
        all_enemies = set()
        
        for i, matchups in enumerate(matchups_list):
            champion_name = f"Champion{i+1}"  # Fallback name, should be passed properly
            
            for enemy, winrate, delta1, delta2, pickrate, games in matchups:
                if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                    all_enemies.add(enemy)
                    if enemy not in enemy_coverage or delta2 > enemy_coverage[enemy][0]:
                        enemy_coverage[enemy] = (delta2, champion_name)
        
        return enemy_coverage

    def _calculate_adaptive_base_weights(self, sample_trios: List[tuple]) -> Dict[str, float]:
        """
        Calculate base weights using variance analysis.
        
        Metrics with higher variance discriminate better between trios,
        so they receive higher weights in the final scoring.
        
        Args:
            sample_trios: List of trio tuples to analyze for variance
            
        Returns:
            Dictionary of normalized base weights
        """
        try:
            if len(sample_trios) < 3:
                # Fallback to equal weights if insufficient data
                return {'coverage': 0.25, 'balance': 0.25, 'consistency': 0.25, 'meta': 0.25}
            
            # Collect scores for all metrics
            metric_scores = {
                'coverage': [],
                'balance': [], 
                'consistency': [],
                'meta': []
            }
            
            if self.verbose:
                print(f"[DEBUG] Calculating adaptive weights from {len(sample_trios)} trios...")
            
            for trio in sample_trios:
                try:
                    # Get individual matchups for the trio
                    matchups = []
                    for champion in trio:
                        champ_matchups = self.db.get_champion_matchups_by_name(champion)
                        if champ_matchups:
                            matchups.append(champ_matchups)
                    
                    if len(matchups) != 3:
                        continue
                    
                    # Calculate individual metric scores
                    enemy_coverage = self._calculate_enemy_coverage(matchups)
                    
                    # Get all enemies for coverage calculation
                    all_enemies = set()
                    for matchup_list in matchups:
                        for enemy, winrate, delta1, delta2, pickrate, games in matchup_list:
                            if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                                all_enemies.add(enemy)
                    
                    metric_scores['coverage'].append(self._calculate_coverage_score(enemy_coverage, all_enemies))
                    metric_scores['balance'].append(self._calculate_balance_score(trio, matchups))
                    metric_scores['consistency'].append(self._calculate_consistency_score(trio, matchups))
                    metric_scores['meta'].append(self._calculate_meta_score(enemy_coverage))
                    
                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error processing trio {trio}: {e}")
                    continue
            
            # Calculate variances
            variances = {}
            for metric, scores in metric_scores.items():
                if len(scores) >= 2:
                    # Use numpy for variance calculation if available, otherwise manual
                    try:
                        import numpy as np
                        variances[metric] = float(np.var(scores))
                    except ImportError:
                        mean_score = sum(scores) / len(scores)
                        variance = sum((x - mean_score) ** 2 for x in scores) / len(scores)
                        variances[metric] = variance
                else:
                    variances[metric] = 1.0  # Fallback
            
            # Normalize variances to weights (higher variance = higher weight)
            total_variance = sum(variances.values())
            if total_variance == 0:
                # All metrics have zero variance - use equal weights
                base_weights = {'coverage': 0.25, 'balance': 0.25, 'consistency': 0.25, 'meta': 0.25}
            else:
                base_weights = {metric: var / total_variance for metric, var in variances.items()}
            
            if self.verbose:
                print(f"[DEBUG] Variance analysis:")
                for metric, variance in variances.items():
                    print(f"  {metric}: variance={variance:.3f}, weight={base_weights[metric]:.3f}")
            
            return base_weights
            
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Adaptive weight calculation failed: {e}")
            # Fallback to equal weights
            return {'coverage': 0.25, 'balance': 0.25, 'consistency': 0.25, 'meta': 0.25}

    def _get_profile_modifiers(self, profile: str = "balanced") -> Dict[str, float]:
        """
        Get profile-specific modifiers for weight adjustment.
        
        Args:
            profile: Scoring profile ("safe", "meta", "aggressive", "balanced")
            
        Returns:
            Dictionary of multipliers for each metric
        """
        profiles = {
            "safe": {
                "consistency": 1.8,    # ++ Fiabilité avant tout
                "balance": 1.2,        # + Diversité pour éviter risques
                "coverage": 0.7,       # - Moins important si on joue safe
                "meta": 0.3           # -- Peu important, on évite les risques
            },
            "meta": {
                "meta": 2.0,          # ++ Performance vs picks populaires
                "consistency": 1.3,    # + Fiabilité dans le meta actuel
                "coverage": 0.8,       # - Couverture moins critique
                "balance": 0.6        # -- Diversité moins importante
            },
            "aggressive": {
                "coverage": 1.5,       # + Maximum de coverage pour dominer
                "balance": 1.3,        # + Diversité pour surprendre
                "consistency": 0.8,    # - Moins critique si on cherche à dominer
                "meta": 0.7           # - Meta moins important
            },
            "balanced": {
                "coverage": 1.0,       # = Garde les poids de variance pure
                "balance": 1.0,
                "consistency": 1.0, 
                "meta": 1.0
            }
        }
        
        return profiles.get(profile, profiles["balanced"])

    def _calculate_contextual_total_score(self, scores: Dict[str, float], profile: str = "balanced") -> tuple:
        """
        Calculate total score using adaptive weights + profile modifiers.
        
        Args:
            scores: Dictionary with individual metric scores
            profile: Scoring profile to apply
            
        Returns:
            Tuple of (total_score, final_weights_used)
        """
        try:
            # 1. Get base weights (calculated once and cached)
            if not hasattr(self, '_cached_base_weights'):
                # Generate sample trios for weight calculation
                sample_trios = self._generate_sample_trios_for_weights()
                self._cached_base_weights = self._calculate_adaptive_base_weights(sample_trios)
                if self.verbose:
                    print(f"[DEBUG] Cached adaptive base weights: {self._cached_base_weights}")
            
            base_weights = self._cached_base_weights
            
            # 2. Get profile modifiers
            modifiers = self._get_profile_modifiers(profile)
            
            # 3. Calculate final weights = base × modifier
            final_weights = {}
            for metric in ['coverage', 'balance', 'consistency', 'meta']:
                final_weights[metric] = base_weights[metric] * modifiers[metric]
            
            # 4. Renormalize so sum = 1.0
            total = sum(final_weights.values())
            if total > 0:
                final_weights = {k: v/total for k, v in final_weights.items()}
            else:
                # Fallback
                final_weights = {'coverage': 0.25, 'balance': 0.25, 'consistency': 0.25, 'meta': 0.25}
            
            # 5. Calculate weighted total score
            total_score = (
                scores['coverage_score'] * final_weights['coverage'] +
                scores['balance_score'] * final_weights['balance'] +
                scores['consistency_score'] * final_weights['consistency'] +
                scores['meta_score'] * final_weights['meta']
            )
            
            return total_score, final_weights
            
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Contextual scoring failed: {e}")
            # Fallback to simple average
            total_score = sum(scores.values()) / len(scores)
            fallback_weights = {'coverage': 0.25, 'balance': 0.25, 'consistency': 0.25, 'meta': 0.25}
            return total_score, fallback_weights

    def _generate_sample_trios_for_weights(self, sample_size: int = 15) -> List[tuple]:
        """
        Generate a sample of trios for adaptive weight calculation.

        Uses a subset of available champions to avoid expensive computation.

        Args:
            sample_size: Number of sample trios to generate

        Returns:
            List of trio tuples
        """
        try:
            from itertools import combinations
            from .constants import (TOP_CHAMPIONS, JUNGLE_CHAMPIONS, MID_CHAMPIONS,
                                  ADC_CHAMPIONS, SUPPORT_CHAMPIONS)

            # Get a balanced sample of champions from different roles
            sample_champions = []

            # Take some champions from each role for diversity
            sample_champions.extend(TOP_CHAMPIONS[:3])
            sample_champions.extend(JUNGLE_CHAMPIONS[:3])
            sample_champions.extend(MID_CHAMPIONS[:3])
            sample_champions.extend(ADC_CHAMPIONS[:2])
            sample_champions.extend(SUPPORT_CHAMPIONS[:2])
            
            # Filter champions that have data in database
            valid_champions = []
            for champion in sample_champions:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if matchups and len(matchups) > 10:  # Ensure sufficient data
                    valid_champions.append(champion)
            
            if len(valid_champions) < 3:
                if self.verbose:
                    print(f"[WARNING] Insufficient champions with data for weight calculation")
                return []
            
            # Generate combinations and take a sample
            all_trios = list(combinations(valid_champions, 3))
            
            # Take a reasonable sample
            import random
            actual_sample_size = min(sample_size, len(all_trios))
            sample_trios = random.sample(all_trios, actual_sample_size)
            
            if self.verbose:
                print(f"[DEBUG] Generated {len(sample_trios)} sample trios from {len(valid_champions)} champions")
            
            return sample_trios
            
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Sample trio generation failed: {e}")
            return []

    def set_scoring_profile(self, profile: str):
        """
        Set the scoring profile for trio evaluation.
        
        Args:
            profile: One of "safe", "meta", "aggressive", "balanced"
        """
        valid_profiles = ["safe", "meta", "aggressive", "balanced"]
        if profile in valid_profiles:
            self.scoring_profile = profile
            # Clear cached weights to recalculate with new profile
            if hasattr(self, '_cached_base_weights'):
                delattr(self, '_cached_base_weights')
            if self.verbose:
                print(f"[INFO] Scoring profile set to: {profile}")
        else:
            if self.verbose:
                print(f"[WARNING] Invalid profile '{profile}'. Valid options: {valid_profiles}")

    def _calculate_blind_pick_score(self, champion: str) -> float:
        """Calculate average delta2 score for a champion as blind pick."""
        try:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if not matchups:
                return 0.0
            return self.avg_delta2(matchups)
        except Exception as e:
            print(f"Error calculating blind pick score for {champion}: {e}")
            return 0.0

    def _find_optimal_counterpick_duo(self, remaining_pool: List[str], blind_champion: str, show_ranking: bool = False) -> tuple:
        """Find the best duo of counterpicks using reverse lookup to maximize coverage against all champions."""
        from itertools import combinations
        
        if len(remaining_pool) < 2:
            raise ValueError(f"Need at least 2 champions in pool, got {len(remaining_pool)}")
        
        duo_rankings = []  # Store all viable duos with their scores
        evaluated_combinations = 0
        
        total_combinations = len(list(combinations(remaining_pool, 2)))
        print(f"Evaluating {total_combinations} possible duos...")
        
        # Try all possible pairs from remaining pool
        for duo in combinations(remaining_pool, 2):
            try:
                trio = [blind_champion] + list(duo)
                trio_score = self._calculate_trio_coverage_reverse(trio)
                
                if trio_score['coverage_ratio'] < 0.3:  # Less than 30% coverage
                    continue
                
                evaluated_combinations += 1
                
                # Store duo info for ranking
                duo_rankings.append({
                    'duo': duo,
                    'total_score': trio_score['total_score'],
                    'coverage': trio_score['coverage_ratio'],
                    'avg_score': trio_score['avg_score'],
                    'matchups_covered': trio_score['covered_count']
                })
                    
            except Exception as e:
                if self.verbose:
                    print(f"Error evaluating duo {duo}: {e}")
                continue
        
        if evaluated_combinations == 0:
            raise ValueError("No valid duo combinations could be evaluated")
        
        # Sort by total score (descending)
        duo_rankings.sort(key=lambda x: x['total_score'], reverse=True)
        
        if not duo_rankings:
            raise ValueError("No viable duo found after evaluation")
        
        # Display rankings if requested
        if show_ranking and len(duo_rankings) > 1:
            safe_print(f"\n📊 TOP DUO RANKINGS:")
            safe_print("─" * 80)
            display_count = min(5, len(duo_rankings))  # Show top 5
            
            for i, info in enumerate(duo_rankings[:display_count]):
                duo = info['duo']
                score = info['total_score']
                coverage = info['coverage']
                avg_score = info['avg_score']
                
                rank_symbol = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                
                safe_print(f"{rank_symbol} {duo[0]} + {duo[1]}")
                print(f"    Total Score: {score:.2f} | Coverage: {coverage:.1%} | Avg/Match: {avg_score:.2f}")
        
        print(f"Evaluated {evaluated_combinations} valid combinations")
        
        best_info = duo_rankings[0]
        return best_info['duo'], best_info['total_score']

    def _calculate_trio_coverage_reverse(self, trio: List[str]) -> dict:
        """
        Calculate trio coverage using reverse lookup approach.
        
        For each enemy champion, find the best counter from our trio directly.
        This avoids duplicate matchups and improves performance.
        
        Args:
            trio: List of 3 champion names
            
        Returns:
            dict: Coverage statistics and scores
        """
        total_score = 0.0
        covered_enemies = 0
        coverage_details = {}  # enemy -> (best_counter, delta2)
        
        for enemy_champion in CHAMPIONS_LIST:
            best_delta2 = -float('inf')
            best_counter = None
            
            # For this enemy, check which champion in our trio counters it best
            for our_champion in trio:
                try:
                    # Use database method to get specific matchup if it exists
                    matchup_delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)
                    
                    if matchup_delta2 is not None and matchup_delta2 > best_delta2:
                        best_delta2 = matchup_delta2
                        best_counter = our_champion
                        
                except Exception as e:
                    if self.verbose:
                        print(f"Error getting matchup {our_champion} vs {enemy_champion}: {e}")
                    continue
            
            # If we found a valid matchup, record it
            if best_counter is not None and best_delta2 != -float('inf'):
                total_score += best_delta2
                covered_enemies += 1
                coverage_details[enemy_champion] = (best_counter, best_delta2)
        
        # Calculate metrics
        total_enemies = len(CHAMPIONS_LIST)
        coverage_ratio = covered_enemies / total_enemies if total_enemies > 0 else 0
        avg_score = total_score / covered_enemies if covered_enemies > 0 else 0
        
        return {
            'total_score': total_score,
            'covered_count': covered_enemies,
            'coverage_ratio': coverage_ratio,
            'avg_score': avg_score,
            'coverage_details': coverage_details
        }

    def optimal_trio_from_pool(self, champion_pool: List[str]) -> tuple:
        """
        Find optimal 3-champion composition from a given pool.
        
        Algorithm:
        1. Validate champion pool data availability
        2. Find champion with best average delta2 as blind pick
        3. From remaining champions, find duo that maximizes counterpick coverage
        
        Args:
            champion_pool: List of champion names to choose from
            
        Returns:
            Tuple of (blind_pick, counterpick1, counterpick2, total_score)
            
        Raises:
            ValueError: If insufficient champions with data available
        """
        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")
        
        print(f"Analyzing optimal trio from pool: {champion_pool}")
        
        # Step 0: Validate champion data availability
        viable_champions, validation_report = self._validate_champion_pool(champion_pool)
        
        if len(viable_champions) < 3:
            safe_print(f"\n❌ ERROR: Only {len(viable_champions)} champions have sufficient data.")
            print("Need at least 3 champions with data to form a trio.")
            print("\nChampions with insufficient data:")
            for champ, data in validation_report.items():
                if not data['has_data']:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")
        
        if len(viable_champions) < len(champion_pool):
            safe_print(f"\n⚠️  WARNING: Using {len(viable_champions)} viable champions out of {len(champion_pool)} requested")
        
        # Step 1: Find best blind pick (highest average delta2) from viable champions
        blind_candidates = []
        
        print(f"\nAnalyzing blind pick candidates from viable champions...")
        for champion in viable_champions:
            score = validation_report[champion]['avg_delta2']
            games = validation_report[champion]['total_games']
            matchups = validation_report[champion]['matchups']
            
            blind_candidates.append({
                'champion': champion,
                'avg_delta2': score,
                'total_games': games,
                'matchups': matchups
            })
        
        # Sort by avg_delta2 (descending)
        blind_candidates.sort(key=lambda x: x['avg_delta2'], reverse=True)
        
        if not blind_candidates:
            raise ValueError("No viable blind pick champion found")
        
        # Display blind pick rankings
        safe_print(f"\n🎯 BLIND PICK RANKINGS:")
        safe_print("─" * 60)
        display_count = min(len(viable_champions), 5)  # Show all viable or max 5
        
        for i, candidate in enumerate(blind_candidates[:display_count]):
            champ = candidate['champion']
            score = candidate['avg_delta2']
            games = candidate['total_games']
            matchups = candidate['matchups']
            
            rank_symbol = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            
            safe_print(f"{rank_symbol} {champ}")
            print(f"    Avg Delta2: {score:.2f} | Games: {games:,} | Matchups: {matchups}")
        
        best_blind = blind_candidates[0]['champion']
        best_blind_score = blind_candidates[0]['avg_delta2']
        
        safe_print(f"\n✅ Selected blind pick: {best_blind} (avg delta2: {best_blind_score:.2f})")
        
        # Step 2: Find best counterpick duo from remaining viable champions
        remaining_pool = [champ for champ in viable_champions if champ != best_blind]
        
        if len(remaining_pool) < 2:
            raise ValueError(f"Insufficient remaining champions for duo: only {len(remaining_pool)} available")
        
        try:
            best_duo, duo_score = self._find_optimal_counterpick_duo(remaining_pool, best_blind, show_ranking=True)
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal counterpick duo: {e}")
        
        if best_duo is None:
            raise ValueError("No viable counterpick duo found")
        
        total_score = best_blind_score + duo_score
        
        print(f"Best counterpick duo: {best_duo}")
        print(f"Total coverage score: {total_score:.2f}")
        safe_print(f"\n✅ Optimal trio: {best_blind} (blind) + {best_duo[0]} + {best_duo[1]} (counterpicks)")
        
        # Add tactical analysis
        result_trio = (best_blind, best_duo[0], best_duo[1], total_score)
        self._analyze_trio_tactics(result_trio)
        
        return result_trio

    def optimal_duo_for_champion(self, fixed_champion: str, champion_pool: List[str] = None) -> tuple:
        """
        Find the best duo of champions to pair with a fixed champion.
        
        Algorithm:
        1. Validate fixed champion has data
        2. Validate companion pool has sufficient data
        3. Find the duo that maximizes total counterpick coverage alongside fixed champion
        
        Args:
            fixed_champion: The champion that must be in the trio
            champion_pool: Pool to choose companions from (default: CHAMPION_POOL)
            
        Returns:
            Tuple of (fixed_champion, companion1, companion2, total_score)
            
        Raises:
            ValueError: If fixed champion or insufficient companions have data
        """
        if champion_pool is None:
            champion_pool = CHAMPION_POOL.copy()
        
        print(f"Finding optimal duo to pair with: {fixed_champion}")
        
        # Step 0: Validate fixed champion has data
        has_data, matchups, games, delta2 = self._validate_champion_data(fixed_champion)
        
        if not has_data:
            safe_print(f"\n❌ ERROR: Fixed champion '{fixed_champion}' has insufficient data")
            print(f"  Matchups: {matchups}, Games: {games}")
            raise ValueError(f"Fixed champion '{fixed_champion}' has insufficient data in database")
        
        safe_print(f"✅ Fixed champion validated: {matchups} matchups, {games} total games, {delta2:.2f} avg delta2")
        
        # Remove the fixed champion from the pool if it's there
        available_pool = [champ for champ in champion_pool if champ.lower() != fixed_champion.lower()]
        
        if len(available_pool) < 2:
            raise ValueError("Champion pool must contain at least 2 champions besides the fixed one")
        
        # Step 1: Validate available companion pool
        viable_companions, validation_report = self._validate_champion_pool(available_pool)
        
        if len(viable_companions) < 2:
            safe_print(f"\n❌ ERROR: Only {len(viable_companions)} companions have sufficient data.")
            print("Need at least 2 viable companions to form a duo.")
            print("\nCompanions with insufficient data:")
            for champ, data in validation_report.items():
                if not data['has_data']:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(f"Insufficient companion data: only {len(viable_companions)}/2 champions viable")
        
        if len(viable_companions) < len(available_pool):
            safe_print(f"\n⚠️  WARNING: Using {len(viable_companions)} viable companions out of {len(available_pool)} available")
        
        # Step 2: Find best duo from viable companions
        try:
            best_duo, duo_score = self._find_optimal_counterpick_duo(viable_companions, fixed_champion, show_ranking=True)
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal companion duo: {e}")
        
        if best_duo is None:
            raise ValueError("No viable companion duo found")
        
        total_score = delta2 + duo_score
        
        print(f"\nBest companions: {best_duo}")
        print(f"Total coverage score: {total_score:.2f}")
        safe_print(f"\n✅ Optimal trio: {fixed_champion} + {best_duo[0]} + {best_duo[1]}")
        
        # Add tactical analysis
        result_trio = (fixed_champion, best_duo[0], best_duo[1], total_score)
        self._analyze_trio_tactics(result_trio)
        
        return result_trio

    def _analyze_trio_tactics(self, trio: tuple) -> None:
        """
        Provide tactical analysis on how to use the optimal trio.
        
        Args:
            trio: (champion1, champion2, champion3) - the optimal trio
        """
        blind_pick, counter1, counter2 = trio[:3]
        
        safe_print(f"\n🎮 TACTICAL ANALYSIS:")
        safe_print("=" * 80)
        print(f"Your optimal trio: {blind_pick} (Blind) + {counter1} + {counter2} (Counterpicks)")
        
        # Analyze each champion's role and best matchups
        trio_champions = [blind_pick, counter1, counter2]
        
        for i, champion in enumerate(trio_champions):
            role = "BLIND PICK" if i == 0 else f"COUNTERPICK #{i}"
            
            try:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if not matchups:
                    continue
                
                # Find best and worst matchups
                valid_matchups = [(m[0], m[3]) for m in matchups if m[5] >= 200]  # enemy, delta2, min 200 games
                valid_matchups.sort(key=lambda x: x[1], reverse=True)  # Sort by delta2
                
                if not valid_matchups:
                    continue
                
                safe_print(f"\n🔸 {champion} ({role}):")
                
                # Best matchups (top 5)
                best_matchups = valid_matchups[:5]
                safe_print(f"  ✅ STRONG AGAINST:")
                for enemy, delta2 in best_matchups:
                    print(f"    • {enemy} ({delta2:+.2f} delta2)")
                
                # Worst matchups (bottom 5, but only show negatives)
                worst_matchups = [m for m in valid_matchups[-10:] if m[1] < 0]  # Only negative deltas
                worst_matchups = sorted(worst_matchups, key=lambda x: x[1])[:5]  # Worst 5
                
                if worst_matchups:
                    safe_print(f"  ⚠️  WEAK AGAINST:")
                    for enemy, delta2 in worst_matchups:
                        print(f"    • {enemy} ({delta2:+.2f} delta2)")
                
                # Neutral matchups count
                neutral_count = sum(1 for _, delta2 in valid_matchups if -1 <= delta2 <= 1)
                safe_print(f"  ➖ NEUTRAL MATCHUPS: {neutral_count} champions")
                
            except Exception as e:
                print(f"  Error analyzing {champion}: {e}")
                continue
        
        # Coverage analysis
        self._analyze_trio_coverage(trio_champions)

    def _analyze_trio_coverage(self, trio: List[str]) -> None:
        """Analyze what the trio covers and potential gaps using reverse lookup."""
        
        safe_print(f"\n📊 COVERAGE ANALYSIS:")
        safe_print("─" * 50)
        
        coverage_map = {}  # enemy -> best_counter_info
        uncovered_enemies = []
        
        # Use efficient reverse lookup
        for enemy_champion in CHAMPIONS_LIST:
            best_counter = None
            best_delta2 = -float('inf')
            
            for our_champion in trio:
                try:
                    delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)
                    
                    if delta2 is not None and delta2 > best_delta2:
                        best_delta2 = delta2
                        best_counter = our_champion
                        
                except Exception:
                    continue
            
            if best_counter and best_delta2 != -float('inf'):
                coverage_map[enemy_champion] = (best_counter, best_delta2)
            else:
                uncovered_enemies.append(enemy_champion)
        
        # Statistics
        total_enemies = len(CHAMPIONS_LIST)
        covered_count = len(coverage_map)
        coverage_percent = (covered_count / total_enemies) * 100
        
        safe_print(f"📈 COVERAGE STATS:")
        print(f"  • Covered: {covered_count}/{total_enemies} champions ({coverage_percent:.2f}%)")
        
        # Categorize coverage quality
        excellent = [(e, c, d) for e, (c, d) in coverage_map.items() if d >= 2.0]
        good = [(e, c, d) for e, (c, d) in coverage_map.items() if 1.0 <= d < 2.0]
        decent = [(e, c, d) for e, (c, d) in coverage_map.items() if 0 <= d < 1.0]
        struggling = [(e, c, d) for e, (c, d) in coverage_map.items() if d < 0]
        
        if excellent:
            safe_print(f"  🟢 EXCELLENT counters: {len(excellent)} ({len(excellent)/covered_count*100:.2f}%)")
        if good:
            safe_print(f"  🟡 GOOD counters: {len(good)} ({len(good)/covered_count*100:.2f}%)")
        if decent:
            safe_print(f"  🟠 DECENT counters: {len(decent)} ({len(decent)/covered_count*100:.2f}%)")
        if struggling:
            safe_print(f"  🔴 STRUGGLING against: {len(struggling)} ({len(struggling)/covered_count*100:.2f}%)")
        
        # Show problematic matchups
        if struggling:
            safe_print(f"\n⚠️  DIFFICULT MATCHUPS:")
            worst_struggling = sorted(struggling, key=lambda x: x[2])[:3]  # Worst 3
            for enemy, counter, delta2 in worst_struggling:
                print(f"    • {enemy}: Best answer is {counter} ({delta2:+.2f} delta2)")
        
        if uncovered_enemies:
            safe_print(f"\n❌ UNCOVERED CHAMPIONS ({len(uncovered_enemies)}):")
            if len(uncovered_enemies) <= 5:
                for enemy in uncovered_enemies:
                    print(f"    • {enemy}")
            else:
                for enemy in uncovered_enemies[:3]:
                    print(f"    • {enemy}")
                print(f"    ... and {len(uncovered_enemies)-3} more")
        
        # Draft recommendations
        safe_print(f"\n💡 DRAFT RECOMMENDATIONS:")
        if coverage_percent >= 85:
            safe_print("  🟢 Excellent pool! Very few gaps.")
        elif coverage_percent >= 70:
            safe_print("  🟡 Good pool with minor gaps.")
        elif coverage_percent >= 50:
            safe_print("  🟠 Decent pool but consider expanding.")
        else:
            safe_print("  🔴 Pool has significant gaps - consider more champions.")

        if len(excellent) > len(struggling):
            safe_print("  📈 Pool favors aggressive counterpicking.")
        else:
            safe_print("  🛡️ Pool requires careful champion selection.")

    # ========== Tier List Generation ==========

    def calculate_blind_pick_score(self, matchups: List[tuple], pool_min_delta2: float = None, pool_max_delta2: float = None, pool_min_variance: float = None, pool_max_variance: float = None, pool_min_coverage: float = None, pool_max_coverage: float = None) -> dict:
        """
        Calculate normalized blind pick score for a champion.

        Blind pick score prioritizes:
        - High average performance across all matchups
        - Low variance (consistency)
        - High coverage of decent matchups

        Args:
            matchups: List of matchup tuples (enemy, winrate, delta1, delta2, pickrate, games)
            pool_min_delta2: Minimum delta2 in the pool (for pool-relative normalization)
            pool_max_delta2: Maximum delta2 in the pool (for pool-relative normalization)
            pool_min_variance: Minimum variance in the pool (for pool-relative normalization)
            pool_max_variance: Maximum variance in the pool (for pool-relative normalization)
            pool_min_coverage: Minimum coverage in the pool (for pool-relative normalization)
            pool_max_coverage: Maximum coverage in the pool (for pool-relative normalization)

        Returns:
            dict: {
                'final_score': float (0-100),
                'avg_performance_norm': float (0-1),
                'avg_delta2_raw': float,
                'stability': float (0-1),
                'variance': float,
                'coverage_norm': float (0-1),
                'coverage_raw': float
            }
        """
        from .config import tierlist_config
        import statistics

        valid_matchups = self._filter_valid_matchups(matchups)

        if not valid_matchups:
            return {
                'final_score': 0.0,
                'avg_performance_norm': 0.0,
                'avg_delta2_raw': 0.0,
                'stability': 0.0,
                'variance': 0.0,
                'coverage_norm': 0.0,
                'coverage_raw': 0.0
            }

        # 1. Performance moyenne (normalisée avec pool-relative ou config ranges)
        avg_delta2_raw = self.avg_delta2(matchups)

        # Use pool-relative normalization if provided, otherwise fall back to config
        if pool_min_delta2 is not None and pool_max_delta2 is not None:
            min_delta2 = pool_min_delta2
            max_delta2 = pool_max_delta2
        else:
            min_delta2 = tierlist_config.MIN_DELTA2
            max_delta2 = tierlist_config.MAX_DELTA2

        avg_performance_norm = (avg_delta2_raw - min_delta2) / (max_delta2 - min_delta2)
        avg_performance_norm = max(0.0, min(1.0, avg_performance_norm))  # Clamp 0-1

        # 2. Stabilité (inverse variance, 0-1)
        delta2_values = [m[3] for m in valid_matchups]
        variance_val = statistics.variance(delta2_values) if len(delta2_values) > 1 else 0.0

        # Use pool-relative normalization if provided, otherwise fall back to formula
        if pool_min_variance is not None and pool_max_variance is not None:
            # Pool-relative: low variance = high stability
            variance_normalized = (variance_val - pool_min_variance) / (pool_max_variance - pool_min_variance)
            variance_normalized = max(0.0, min(1.0, variance_normalized))  # Clamp 0-1
            stability = 1.0 - variance_normalized  # Invert: low variance = high stability
        else:
            # Fallback to old formula
            stability = 1 / (1 + variance_val)

        # 3. Couverture (proportion matchups décents, pool-relative normalization)
        decent_weight = sum(m[4] for m in matchups if m[3] > tierlist_config.DECENT_MATCHUP_THRESHOLD)
        total_weight = sum(m[4] for m in matchups)
        coverage_raw = decent_weight / total_weight if total_weight > 0 else 0.0

        # Use pool-relative normalization if provided, otherwise use raw coverage
        if pool_min_coverage is not None and pool_max_coverage is not None:
            coverage_norm = (coverage_raw - pool_min_coverage) / (pool_max_coverage - pool_min_coverage)
            coverage_norm = max(0.0, min(1.0, coverage_norm))  # Clamp 0-1
        else:
            coverage_norm = coverage_raw  # Already 0-1

        # Score composite (0-1)
        normalized_score = (
            avg_performance_norm * tierlist_config.BLIND_AVG_WEIGHT +
            stability * tierlist_config.BLIND_STABILITY_WEIGHT +
            coverage_norm * tierlist_config.BLIND_COVERAGE_WEIGHT
        )

        # Convertir en 0-100
        final_score = normalized_score * 100

        return {
            'final_score': final_score,
            'avg_performance_norm': avg_performance_norm,
            'avg_delta2_raw': avg_delta2_raw,
            'stability': stability,
            'variance': variance_val,
            'coverage_norm': coverage_norm,
            'coverage_raw': coverage_raw
        }

    def calculate_counter_pick_score(self, matchups: List[tuple],
                                      pool_min_peak_impact: float = None,
                                      pool_max_peak_impact: float = None,
                                      pool_min_variance: float = None,
                                      pool_max_variance: float = None,
                                      pool_min_target_ratio: float = None,
                                      pool_max_target_ratio: float = None) -> dict:
        """
        Calculate normalized counter pick score for a champion.

        Counter pick score prioritizes:
        - High impact in excellent/good matchups (weighted by pickrate)
        - High variance (volatility indicates situational strength)
        - High proportion of viable counterpick targets

        Args:
            matchups: List of matchup tuples (enemy, winrate, delta1, delta2, pickrate, games)
            pool_min_peak_impact: Minimum peak_impact in the pool (for pool-relative normalization)
            pool_max_peak_impact: Maximum peak_impact in the pool (for pool-relative normalization)
            pool_min_variance: Minimum variance in the pool (for pool-relative normalization)
            pool_max_variance: Maximum variance in the pool (for pool-relative normalization)
            pool_min_target_ratio: Minimum target_ratio in the pool (for pool-relative normalization)
            pool_max_target_ratio: Maximum target_ratio in the pool (for pool-relative normalization)

        Returns:
            dict: {
                'final_score': float (0-100),
                'peak_impact_norm': float (0-1),
                'peak_impact_raw': float,
                'volatility_norm': float (0-1),
                'variance': float,
                'target_ratio_norm': float (0-1),
                'target_ratio_raw': float
            }
        """
        from .config import tierlist_config
        import statistics

        valid_matchups = self._filter_valid_matchups(matchups)

        if not valid_matchups:
            return {
                'final_score': 0.0,
                'peak_impact_norm': 0.0,
                'peak_impact_raw': 0.0,
                'volatility_norm': 0.0,
                'variance': 0.0,
                'target_ratio_norm': 0.0,
                'target_ratio_raw': 0.0
            }

        # 1. Impact pondéré dans bons matchups (pool-relative normalization)
        excellent_impact = sum(m[3] * m[4] for m in matchups
                              if m[3] > tierlist_config.EXCELLENT_MATCHUP_THRESHOLD)
        good_impact = sum(m[3] * m[4] for m in matchups
                          if tierlist_config.GOOD_MATCHUP_THRESHOLD < m[3] <= tierlist_config.EXCELLENT_MATCHUP_THRESHOLD)
        peak_impact_raw = excellent_impact + good_impact * 0.5  # Excellent matchups count more

        # Use pool-relative normalization if provided, otherwise fall back to config
        if pool_min_peak_impact is not None and pool_max_peak_impact is not None:
            peak_impact_norm = (peak_impact_raw - pool_min_peak_impact) / (pool_max_peak_impact - pool_min_peak_impact)
            peak_impact_norm = max(0.0, min(1.0, peak_impact_norm))  # Clamp 0-1
        else:
            peak_impact_norm = min(peak_impact_raw / tierlist_config.MAX_PEAK_IMPACT, 1.0)

        # 2. Volatilité (variance normalisée, 0-1)
        delta2_values = [m[3] for m in valid_matchups]
        variance_val = statistics.variance(delta2_values) if len(delta2_values) > 1 else 0.0

        # Use pool-relative normalization if provided, otherwise fall back to config
        if pool_min_variance is not None and pool_max_variance is not None:
            volatility_norm = (variance_val - pool_min_variance) / (pool_max_variance - pool_min_variance)
            volatility_norm = max(0.0, min(1.0, volatility_norm))  # Clamp 0-1
        else:
            volatility_norm = min(variance_val / tierlist_config.MAX_VARIANCE, 1.0)

        # 3. Proportion cibles viables (pool-relative normalization)
        viable_weight = sum(m[4] for m in matchups if m[3] > tierlist_config.GOOD_MATCHUP_THRESHOLD)
        total_weight = sum(m[4] for m in matchups)
        target_ratio_raw = viable_weight / total_weight if total_weight > 0 else 0.0

        # Use pool-relative normalization if provided, otherwise use raw ratio
        if pool_min_target_ratio is not None and pool_max_target_ratio is not None:
            target_ratio_norm = (target_ratio_raw - pool_min_target_ratio) / (pool_max_target_ratio - pool_min_target_ratio)
            target_ratio_norm = max(0.0, min(1.0, target_ratio_norm))  # Clamp 0-1
        else:
            target_ratio_norm = target_ratio_raw  # Already 0-1

        # Score composite (0-1)
        normalized_score = (
            peak_impact_norm * tierlist_config.COUNTER_PEAK_WEIGHT +
            volatility_norm * tierlist_config.COUNTER_VOLATILITY_WEIGHT +
            target_ratio_norm * tierlist_config.COUNTER_TARGETS_WEIGHT
        )

        # Convertir en 0-100
        final_score = normalized_score * 100

        return {
            'final_score': final_score,
            'peak_impact_norm': peak_impact_norm,
            'peak_impact_raw': peak_impact_raw,
            'volatility_norm': volatility_norm,
            'variance': variance_val,
            'target_ratio_norm': target_ratio_norm,
            'target_ratio_raw': target_ratio_raw
        }

    def generate_tier_list(self, champion_pool: List[str], analysis_type: str = "blind_pick") -> List[dict]:
        """
        Generate a tier list for a champion pool using pre-computed global scores.

        Uses global normalization: normalizes metrics based on ALL champions in the
        database, making scores comparable across different pools.

        Args:
            champion_pool: List of champion names to include in tier list
            analysis_type: "blind_pick" or "counter_pick"

        Returns:
            List of dicts sorted by score (descending), each containing:
            {
                'champion': str,
                'tier': str ('S', 'A', 'B', or 'C'),
                'score': float (0-100),
                'metrics': dict (detailed metrics)
            }
        """
        from .config import tierlist_config
        import statistics

        # Check if champion_scores table exists and has data
        if not self.db.champion_scores_table_exists():
            print("[WARNING] Champion scores not found in database.")
            print("[INFO] Please run 'Parse Match Statistics' to generate scores first.")
            return []

        # Step 1: Collect all scores from database for global normalization
        all_scores_data = self.db.get_all_champion_scores()

        if not all_scores_data:
            print("[ERROR] No champion scores found in database")
            return []

        # Extract global ranges for normalization
        all_metrics = {
            'avg_delta2': [],
            'variance': [],
            'coverage': [],
            'peak_impact': [],
            'volatility': [],
            'target_ratio': []
        }

        for row in all_scores_data:
            # row = (name, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
            all_metrics['avg_delta2'].append(row[1])
            all_metrics['variance'].append(row[2])
            all_metrics['coverage'].append(row[3])
            all_metrics['peak_impact'].append(row[4])
            all_metrics['volatility'].append(row[5])
            all_metrics['target_ratio'].append(row[6])

        # Calculate global ranges
        min_delta2_global = min(all_metrics['avg_delta2'])
        max_delta2_global = max(all_metrics['avg_delta2'])
        min_variance_global = min(all_metrics['variance'])
        max_variance_global = max(all_metrics['variance'])
        min_coverage_global = min(all_metrics['coverage'])
        max_coverage_global = max(all_metrics['coverage'])
        min_peak_impact_global = min(all_metrics['peak_impact'])
        max_peak_impact_global = max(all_metrics['peak_impact'])
        min_target_ratio_global = min(all_metrics['target_ratio'])
        max_target_ratio_global = max(all_metrics['target_ratio'])

        # Avoid division by zero
        if max_delta2_global == min_delta2_global:
            min_delta2_global -= 0.05
            max_delta2_global += 0.05
        if max_variance_global == min_variance_global:
            min_variance_global -= 0.05
            max_variance_global += 0.05
        if max_coverage_global == min_coverage_global:
            min_coverage_global -= 0.05
            max_coverage_global += 0.05
        if max_peak_impact_global == min_peak_impact_global:
            min_peak_impact_global -= 0.5
            max_peak_impact_global += 0.5
        if max_target_ratio_global == min_target_ratio_global:
            min_target_ratio_global -= 0.05
            max_target_ratio_global += 0.05

        if self.verbose:
            print(f"[INFO] Global normalization ranges:")
            print(f"  Delta2: {min_delta2_global:.2f} to {max_delta2_global:.2f}")
            print(f"  Variance: {min_variance_global:.2f} to {max_variance_global:.2f}")
            if analysis_type == "blind_pick":
                print(f"  Coverage: {min_coverage_global:.3f} to {max_coverage_global:.3f}")
            elif analysis_type == "counter_pick":
                print(f"  Peak Impact: {min_peak_impact_global:.3f} to {max_peak_impact_global:.3f}")
                print(f"  Target Ratio: {min_target_ratio_global:.3f} to {max_target_ratio_global:.3f}")

        # Step 2: Get scores from database and calculate normalized scores
        results = []

        for champion in champion_pool:
            # Get pre-computed scores from database
            scores = self.db.get_champion_scores_by_name(champion)

            if scores is None:
                if self.verbose:
                    print(f"  [SKIP] {champion}: No scores in database")
                continue

            # Calculate normalized score based on analysis type
            if analysis_type == "blind_pick":
                # Normalize components
                avg_perf_norm = (scores['avg_delta2'] - min_delta2_global) / (max_delta2_global - min_delta2_global)
                avg_perf_norm = max(0.0, min(1.0, avg_perf_norm))

                variance_norm = (scores['variance'] - min_variance_global) / (max_variance_global - min_variance_global)
                variance_norm = max(0.0, min(1.0, variance_norm))
                stability = 1.0 - variance_norm  # Invert: low variance = high stability

                coverage_norm = (scores['coverage'] - min_coverage_global) / (max_coverage_global - min_coverage_global)
                coverage_norm = max(0.0, min(1.0, coverage_norm))

                # Calculate final score
                normalized_score = (
                    avg_perf_norm * tierlist_config.BLIND_AVG_WEIGHT +
                    stability * tierlist_config.BLIND_STABILITY_WEIGHT +
                    coverage_norm * tierlist_config.BLIND_COVERAGE_WEIGHT
                )
                final_score = normalized_score * 100

                # Build metrics dict for display
                metrics = {
                    'final_score': final_score,
                    'avg_performance_norm': avg_perf_norm,
                    'avg_delta2_raw': scores['avg_delta2'],
                    'stability': stability,
                    'variance': scores['variance'],
                    'coverage_norm': coverage_norm,
                    'coverage_raw': scores['coverage']
                }

            elif analysis_type == "counter_pick":
                # Normalize components
                peak_impact_norm = (scores['peak_impact'] - min_peak_impact_global) / (max_peak_impact_global - min_peak_impact_global)
                peak_impact_norm = max(0.0, min(1.0, peak_impact_norm))

                volatility_norm = (scores['volatility'] - min_variance_global) / (max_variance_global - min_variance_global)
                volatility_norm = max(0.0, min(1.0, volatility_norm))

                target_ratio_norm = (scores['target_ratio'] - min_target_ratio_global) / (max_target_ratio_global - min_target_ratio_global)
                target_ratio_norm = max(0.0, min(1.0, target_ratio_norm))

                # Calculate final score
                normalized_score = (
                    peak_impact_norm * tierlist_config.COUNTER_PEAK_WEIGHT +
                    volatility_norm * tierlist_config.COUNTER_VOLATILITY_WEIGHT +
                    target_ratio_norm * tierlist_config.COUNTER_TARGETS_WEIGHT
                )
                final_score = normalized_score * 100

                # Build metrics dict for display
                metrics = {
                    'final_score': final_score,
                    'peak_impact_norm': peak_impact_norm,
                    'peak_impact_raw': scores['peak_impact'],
                    'volatility_norm': volatility_norm,
                    'variance': scores['volatility'],
                    'target_ratio_norm': target_ratio_norm,
                    'target_ratio_raw': scores['target_ratio']
                }

            else:
                raise ValueError(f"Unknown analysis type: {analysis_type}")

            # Determine tier
            if final_score >= tierlist_config.S_TIER_THRESHOLD:
                tier = "S"
            elif final_score >= tierlist_config.A_TIER_THRESHOLD:
                tier = "A"
            elif final_score >= tierlist_config.B_TIER_THRESHOLD:
                tier = "B"
            else:
                tier = "C"

            results.append({
                'champion': champion,
                'tier': tier,
                'score': final_score,
                'metrics': metrics
            })

        # Sort by score (descending)
        results.sort(key=lambda x: x['score'], reverse=True)

        return results

    def calculate_global_scores(self) -> int:
        """
        Calculate and save scores for all champions in the database.

        This function computes raw metrics (avg_delta2, variance, coverage,
        peak_impact, volatility, target_ratio) for all champions and stores
        them in the champion_scores table.

        Should be called after parsing/updating matchup data.

        Returns:
            Number of champions scored and saved
        """
        from .constants import CHAMPIONS_LIST
        from .config import tierlist_config
        import statistics

        print("[INFO] Calculating global champion scores...")

        champions_scored = 0

        for champion in CHAMPIONS_LIST:
            try:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if not matchups:
                    if self.verbose:
                        print(f"  [SKIP] {champion}: No matchups found")
                    continue

                valid_matchups = self._filter_valid_matchups(matchups)
                if not valid_matchups:
                    if self.verbose:
                        print(f"  [SKIP] {champion}: No valid matchups after filtering")
                    continue

                # Calculate raw metrics
                avg_delta2 = self.avg_delta2(matchups)

                delta2_values = [m[3] for m in valid_matchups]
                variance = statistics.variance(delta2_values) if len(delta2_values) > 1 else 0.0

                # Coverage (blind pick metric)
                decent_weight = sum(m[4] for m in matchups if m[3] > tierlist_config.DECENT_MATCHUP_THRESHOLD)
                total_weight = sum(m[4] for m in matchups)
                coverage = decent_weight / total_weight if total_weight > 0 else 0.0

                # Peak impact (counter pick metric)
                excellent_impact = sum(m[3] * m[4] for m in matchups
                                      if m[3] > tierlist_config.EXCELLENT_MATCHUP_THRESHOLD)
                good_impact = sum(m[3] * m[4] for m in matchups
                                  if tierlist_config.GOOD_MATCHUP_THRESHOLD < m[3] <= tierlist_config.EXCELLENT_MATCHUP_THRESHOLD)
                peak_impact = excellent_impact + good_impact * 0.5

                # Volatility (counter pick metric) - same as variance
                volatility = variance

                # Target ratio (counter pick metric)
                viable_weight = sum(m[4] for m in matchups if m[3] > tierlist_config.GOOD_MATCHUP_THRESHOLD)
                target_ratio = viable_weight / total_weight if total_weight > 0 else 0.0

                # Get champion ID and save scores
                champion_id = self.db.get_champion_id(champion)
                if champion_id is None:
                    if self.verbose:
                        print(f"  [ERROR] {champion}: Could not get champion ID")
                    continue

                self.db.save_champion_scores(
                    champion_id=champion_id,
                    avg_delta2=avg_delta2,
                    variance=variance,
                    coverage=coverage,
                    peak_impact=peak_impact,
                    volatility=volatility,
                    target_ratio=target_ratio
                )

                champions_scored += 1
                if self.verbose:
                    print(f"  ✓ {champion}: avg_delta2={avg_delta2:.3f}, variance={variance:.3f}, coverage={coverage:.3f}")

            except Exception as e:
                print(f"  [ERROR] {champion}: {e}")
                continue

        print(f"[SUCCESS] Scored {champions_scored}/{len(CHAMPIONS_LIST)} champions")
        return champions_scored