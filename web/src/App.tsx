import { useState, useEffect } from 'react'
import './App.css'
import PlayerStatsTable from './components/PlayerStatsTable';
import TeamStatsForm from './components/TeamStatsForm';
import type { Game, Season } from './types/types'

  function scoreClass(score: number, opponent: number): string {
   if (score === opponent){
    return "score-tie"
   }
   else if (score > opponent){
    return "score-win"
   }
   else{
      return "score-loss"
    }
  }

function App() {
  const [games, setGames] = useState<Game[]>([])
  const [seasons, setSeasons] = useState<Season[]>([])
  const [selectedGame, setSelectedGame] = useState<Game | null>(null)
  const [activeTab, setActiveTab] = useState("team")
  const [seasonId, setSeasonId] = useState("1")
  const [weekNumber, setWeekNumber] = useState(1)
  const WEEKS = Array.from({ length: 21 }, (_, i) => i + 1)
  // games
  useEffect(() =>{
      fetch(`http://localhost:8000/games?seasonId=${seasonId}&week=${weekNumber}`)
  .then(res => res.json())
  .then(data => { console.log(data); setGames(data) })

  }, [seasonId, weekNumber]);

// season
  useEffect(() =>{
    fetch(`http://localhost:8000/seasons`)
.then(res => res.json())
.then(data => { console.log("seasons: ", data); setSeasons(data) })

}, []);



  return (
    <>
<select value={seasonId} onChange={e => setSeasonId(e.target.value)}>
{seasons.map(s => (
  <option key={s.id} value={s.id}>{s.name}</option>
))}
</select>
<select value={weekNumber} onChange={e => setWeekNumber(Number(e.target.value))}>
  {WEEKS.map(w => (
    <option key={w} value={w}>Week {w}</option>
  ))}
</select>
{selectedGame ? (
  
  <div>
    <div><button className='back-button' onClick={() => setSelectedGame(null)}>Back</button></div>
    <img alt={selectedGame.awayTeamId} className='logo'src={`/logos/${selectedGame.awayTeamId}.png`}/> 
  <span className={scoreClass(selectedGame.awayScore, selectedGame.homeScore)}>
  {selectedGame.awayScore}
</span> @ <img alt={selectedGame.homeTeamId} className='logo'src={`/logos/${selectedGame.homeTeamId}.png`}/> <span className={scoreClass(selectedGame.homeScore, selectedGame.awayScore)}>
  {selectedGame.homeScore}
</span>

<div>
<button onClick={() => setActiveTab("team")}>Team Stats</button>
<button onClick={() => setActiveTab("away")}>{selectedGame.awayTeamId}</button>
<button onClick={() => setActiveTab("home")}>{selectedGame.homeTeamId}</button>

{activeTab === "team" && <div>
  
<TeamStatsForm
  gameId={selectedGame.id}
  teamId={selectedGame.awayTeamId}
  opponentId={selectedGame.homeTeamId}
  isHome={false}
/>
  
  <TeamStatsForm
  gameId={selectedGame.id}
  teamId={selectedGame.homeTeamId}
  opponentId={selectedGame.awayTeamId}
  isHome={true}
/>
</div>}
{activeTab === "away" && (
  <PlayerStatsTable
    gameId={selectedGame.id}
    seasonId={seasonId}
    teamId={selectedGame.awayTeamId}
    opponentId={selectedGame.homeTeamId}
    isHome={false}
  />
)}
{activeTab === "home" && (
  <PlayerStatsTable
    gameId={selectedGame.id}
    seasonId={selectedGame.seasonId}
    teamId={selectedGame.homeTeamId}
    opponentId={selectedGame.awayTeamId}
    isHome={true}
  />
)}
</div>
</div>
) : (
    <div>
{games.map(game => (
    <div key={game.id} className='game' onClick={() => setSelectedGame(game)}><img alt={game.awayTeamId} className='logo'src={`/logos/${game.awayTeamId}.png`}/> <span className={scoreClass(game.awayScore, game.homeScore)}>
  {game.awayScore}
</span> @ <img alt={game.homeTeamId} className='logo'src={`/logos/${game.homeTeamId}.png`}/> <span className={scoreClass(game.homeScore, game.awayScore)}>
  {game.homeScore}
</span></div>

))}
    </div>
    )}
    </>
  )
}

export default App

