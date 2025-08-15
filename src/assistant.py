from typing import List
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
            '🟢': 'GREEN', '🔴': 'RED', '📊': 'STATS'
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
        return sum(m[2] * m[4] for m in valid_matchups) / len(valid_matchups)

    def avg_delta2(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta2 from valid matchups."""
        valid_matchups = self._filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        return sum(m[3] * m[4] for m in valid_matchups) / len(valid_matchups)
    
    def avg_winrate(self, matchups: List[tuple]) -> float:
        """Calculate weighted average winrate from valid matchups."""
        valid_matchups = self._filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        return sum(m[1] * m[4] for m in valid_matchups) / len(valid_matchups)

    def score_against_team(self, matchups: List[tuple], team: List[str]) -> float:
        """Calculate score against a specific team composition."""
        score = 0
        remaining_matchups = matchups.copy()  # Don't modify the original list
        blind_picks = 5 - len(team)
        
        for enemy in team:
            for i, matchup in enumerate(remaining_matchups):
                if matchup[0].lower() == enemy.lower():
                    score += matchup[3]  # Add delta2 score
                    remaining_matchups.pop(i)
                    break
        
        score += blind_picks * self.avg_delta2(remaining_matchups)
        return score

    def tierlist_delta1(self, champion_list: List[str]) -> List[tuple]:
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.MIN_GAMES:
                break
            score = self.avg_delta1(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def tierlist_delta2(self, champion_list) -> List[tuple]:
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.MIN_GAMES:
                break
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
                score = self.score_against_team(matchups, enemy_team)
                scores.append((str(champion), score))
                scores.sort(key=lambda x: -x[1])

        for index in range(min(_results, len(CHAMPION_POOL))):
            print(scores[index])
        while (input("Want more ?") == "y"):
            _results += nb_results
            for index in range(_results):
                print(scores[index])

    def _calculate_and_display_recommendations(self, enemy_team: List[str], ally_team: List[str], nb_results: int, champion_pool: List[str] = None) -> None:
        """Calculate champion recommendations and display top results."""
        if champion_pool is None:
            champion_pool = SOLOQ_POOL
        
        scores = []
        
        for champion in champion_pool:
            if champion not in enemy_team and champion not in ally_team:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if sum(m[5] for m in matchups) < config.MIN_GAMES_COMPETITIVE:
                    continue
                score = self.score_against_team(matchups, enemy_team)
                scores.append((str(champion), score))
        
        scores.sort(key=lambda x: -x[1])
        
        for index in range(min(nb_results, len(scores))):
            print(scores[index])
    
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
    
    def score_teams(self, team1: List[str], team2: List[str]) -> None:
        scores1 = []
        for i in range(len(team1)):
            scores1.append((team1[i], self.score_against_team(self.db.get_champion_matchups_by_name(team1[i]), team2)))
        scores2 = []
        for i in range(len(team2)):
            scores2.append((team2[i], self.score_against_team(self.db.get_champion_matchups_by_name(team2[i]), team1)))
        
        print("=============")
        sm = 0
        for i in range(len(scores1)):
            print(f"{scores1[i][0]} - {scores1[i][1]}")
            sm += scores1[i][1]
        print("---------")
        print(sm/5)
        
        print("=============")
        sm = 0
        for i in range(len(scores2)):
            print(f"{scores2[i][0]} - {scores2[i][1]}")
            sm += scores2[i][1]
        print("---------")
        print(sm/5)
    
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
        Get ban recommendations against a specific champion pool.
        
        Args:
            champion_pool: List of champion names in your pool
            num_bans: Number of ban recommendations to return
            
        Returns:
            List of tuples (champion_name, threat_score, matchup_count)
            Sorted by threat_score (descending)
        """
        threat_scores = {}  # champion_name -> (total_threat, matchup_count)
        
        # Calculate threat score for each potential ban target
        for our_champion in champion_pool:
            try:
                # Get all matchups for our champion
                matchups = self.db.get_champion_matchups_by_name(our_champion)
                if not matchups:
                    continue
                    
                # For each enemy in our champion's matchups
                for enemy_name, winrate, delta1, delta2, pickrate, games in matchups:
                    # Skip if insufficient data
                    if pickrate < config.MIN_PICKRATE or games < config.MIN_MATCHUP_GAMES:
                        continue
                    
                    # Calculate threat: negative delta2 means enemy is strong against us
                    # We want to ban champions that have positive winrates/deltas against us
                    threat_value = -delta2 * pickrate  # Weight by pickrate
                    
                    if enemy_name not in threat_scores:
                        threat_scores[enemy_name] = [0.0, 0]
                    
                    threat_scores[enemy_name][0] += threat_value
                    threat_scores[enemy_name][1] += 1
                    
            except Exception as e:
                if self.verbose:
                    print(f"Error calculating threats for {our_champion}: {e}")
                continue
        
        # Calculate average threat and filter
        ban_candidates = []
        for enemy_name, (total_threat, matchup_count) in threat_scores.items():
            if matchup_count >= 2:  # Must threaten at least 2 of our champions
                avg_threat = total_threat / matchup_count
                ban_candidates.append((enemy_name, avg_threat, matchup_count))
        
        # Sort by threat score (descending) and return top recommendations
        ban_candidates.sort(key=lambda x: x[1], reverse=True)
        return ban_candidates[:num_bans]

    def find_optimal_trios_holistic(self, champion_pool: List[str], num_results: int = 5) -> List[dict]:
        """
        Find optimal 3-champion combinations using holistic evaluation.
        
        Unlike the blind-pick approach, this evaluates all possible trios as complete units.
        
        Args:
            champion_pool: List of champion names to choose from
            num_results: Number of top trios to return
            
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
        Evaluate a trio of champions using holistic scoring.
        
        Returns dict with individual scores and total score.
        """
        champion1, champion2, champion3 = trio
        
        # Get matchup data for all three champions
        matchups1 = self.db.get_champion_matchups_by_name(champion1)
        matchups2 = self.db.get_champion_matchups_by_name(champion2)  
        matchups3 = self.db.get_champion_matchups_by_name(champion3)
        
        # Create enemy -> best_delta2 mapping for the trio
        enemy_coverage = {}  # enemy_name -> (best_delta2, champion_handling_it)
        all_enemies = set()
        
        # Process matchups for champion1
        for enemy, winrate, delta1, delta2, pickrate, games in matchups1:
            if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                all_enemies.add(enemy)
                if enemy not in enemy_coverage or delta2 > enemy_coverage[enemy][0]:
                    enemy_coverage[enemy] = (delta2, champion1)
        
        # Process matchups for champion2  
        for enemy, winrate, delta1, delta2, pickrate, games in matchups2:
            if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                all_enemies.add(enemy)
                if enemy not in enemy_coverage or delta2 > enemy_coverage[enemy][0]:
                    enemy_coverage[enemy] = (delta2, champion2)
        
        # Process matchups for champion3
        for enemy, winrate, delta1, delta2, pickrate, games in matchups3:
            if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                all_enemies.add(enemy)
                if enemy not in enemy_coverage or delta2 > enemy_coverage[enemy][0]:
                    enemy_coverage[enemy] = (delta2, champion3)
        
        # Calculate individual scores
        coverage_score = self._calculate_coverage_score(enemy_coverage, all_enemies)
        balance_score = self._calculate_balance_score(trio, [matchups1, matchups2, matchups3])
        consistency_score = self._calculate_consistency_score(trio, [matchups1, matchups2, matchups3])
        meta_score = self._calculate_meta_score(enemy_coverage)
        
        # Weighted total score
        total_score = (
            coverage_score * 0.4 +      # Most important: can we handle enemies?
            balance_score * 0.25 +      # Important: diverse profiles
            consistency_score * 0.25 +  # Important: reliable performance  
            meta_score * 0.1           # Nice to have: meta relevance
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
        """Calculate performance against popular/meta champions."""
        # This could be enhanced to use actual meta data, but for now
        # we'll use a simplified approach based on champions that appear frequently
        try:
            # Popular champions that are commonly seen (this could be data-driven)
            meta_champions = [
                'Aatrox', 'Ambessa', 'Fiora', 'Jax', 'Camille', 'Riven', 'Irelia',
                'Gragas', 'Graves', 'Karthus', 'Hecarim', 'Viego', 
                'Yasuo', 'Sylas', 'Azir', 'Corki', 'Viktor',
                'Jinx', 'Caitlyn', 'Aphelios', 'Varus', 'KaiSa',
                'Thresh', 'Nautilus', 'Leona', 'Pyke', 'Rakan'
            ]
            
            meta_scores = []
            for enemy, (delta2, _) in enemy_coverage.items():
                if enemy in meta_champions:
                    meta_scores.append(max(0, delta2))
            
            if not meta_scores:
                return 50.0  # Neutral if no meta coverage
            
            avg_meta_score = sum(meta_scores) / len(meta_scores)
            return min(100.0, (avg_meta_score + 5) * 10)  # Scale to 0-100
            
        except:
            return 50.0

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
        """Find the best duo of counterpicks to maximize coverage against all champions."""
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
                total_score = 0
                trio = [blind_champion] + list(duo)
                valid_matchups_found = 0
                
                # For each enemy champion, find the best counter from our trio
                for enemy_champion in CHAMPIONS_LIST:
                    best_counter_score = -float('inf')
                    
                    for our_champion in trio:
                        try:
                            matchups = self.db.get_champion_matchups_by_name(our_champion)
                            if not matchups:
                                continue
                                
                            # Find the specific matchup against this enemy
                            for matchup in matchups:
                                if matchup[0].lower() == enemy_champion.lower():
                                    if matchup[3] > best_counter_score:  # delta2 is at index 3
                                        best_counter_score = matchup[3]
                                    break
                        except Exception as e:
                            continue  # Skip silently for cleaner output
                    
                    # If we found a matchup, add it to total score
                    if best_counter_score != -float('inf'):
                        total_score += best_counter_score
                        valid_matchups_found += 1
                
                # Calculate coverage metrics
                coverage_ratio = valid_matchups_found / len(CHAMPIONS_LIST)
                avg_score_per_matchup = total_score / valid_matchups_found if valid_matchups_found > 0 else 0
                
                # Only consider this duo if it has reasonable coverage
                if coverage_ratio < 0.3:  # Less than 30% coverage
                    continue
                
                evaluated_combinations += 1
                
                # Store duo info for ranking
                duo_rankings.append({
                    'duo': duo,
                    'total_score': total_score,
                    'coverage': coverage_ratio,
                    'avg_score': avg_score_per_matchup,
                    'matchups_covered': valid_matchups_found
                })
                    
            except Exception as e:
                continue  # Skip silently for cleaner output
        
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
                print(f"    Total Score: {score:.1f} | Coverage: {coverage:.1%} | Avg/Match: {avg_score:.2f}")
        
        print(f"Evaluated {evaluated_combinations} valid combinations")
        
        best_info = duo_rankings[0]
        return best_info['duo'], best_info['total_score']

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
        """Analyze what the trio covers and potential gaps."""
        
        safe_print(f"\n📊 COVERAGE ANALYSIS:")
        safe_print("─" * 50)
        
        coverage_map = {}  # enemy -> best_counter_info
        uncovered_enemies = []
        
        for enemy_champion in CHAMPIONS_LIST:
            best_counter = None
            best_delta2 = -float('inf')
            
            for our_champion in trio:
                try:
                    matchups = self.db.get_champion_matchups_by_name(our_champion)
                    
                    for matchup in matchups:
                        if matchup[0].lower() == enemy_champion.lower():
                            if matchup[3] > best_delta2:  # delta2 better
                                best_delta2 = matchup[3]
                                best_counter = our_champion
                            break
                except:
                    continue
            
            if best_counter:
                coverage_map[enemy_champion] = (best_counter, best_delta2)
            else:
                uncovered_enemies.append(enemy_champion)
        
        # Statistics
        total_enemies = len(CHAMPIONS_LIST)
        covered_count = len(coverage_map)
        coverage_percent = (covered_count / total_enemies) * 100
        
        safe_print(f"📈 COVERAGE STATS:")
        print(f"  • Covered: {covered_count}/{total_enemies} champions ({coverage_percent:.1f}%)")
        
        # Categorize coverage quality
        excellent = [(e, c, d) for e, (c, d) in coverage_map.items() if d >= 2.0]
        good = [(e, c, d) for e, (c, d) in coverage_map.items() if 1.0 <= d < 2.0]
        decent = [(e, c, d) for e, (c, d) in coverage_map.items() if 0 <= d < 1.0]
        struggling = [(e, c, d) for e, (c, d) in coverage_map.items() if d < 0]
        
        if excellent:
            safe_print(f"  🟢 EXCELLENT counters: {len(excellent)} ({len(excellent)/covered_count*100:.1f}%)")
        if good:
            safe_print(f"  🟡 GOOD counters: {len(good)} ({len(good)/covered_count*100:.1f}%)")
        if decent:
            safe_print(f"  🟠 DECENT counters: {len(decent)} ({len(decent)/covered_count*100:.1f}%)")
        if struggling:
            safe_print(f"  🔴 STRUGGLING against: {len(struggling)} ({len(struggling)/covered_count*100:.1f}%)")
        
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