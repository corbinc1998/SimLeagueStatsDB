import { useState, useEffect } from 'react'
import './App.css'

interface Game { 
  id: string;
  homeTeamId: string;
  awayTeamId: string;
  homeScore: number;
  awayScore: number;
  }

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

// test
function App() {
  const [games, setGames] = useState<Game[]>([])
  const [seasonId, setSeasonId] = useState(1)
  const [weekNumber, setWeekNumber] = useState(1)
  useEffect(() =>{
      fetch(`http://localhost:8000/games?seasonId=${seasonId}&week=${weekNumber}`)
  .then(res => res.json())
  .then(data => { console.log(data); setGames(data) })

  }, [seasonId, weekNumber]);



  return (
    <div>
{games.map(game => (
    <div key={game.id} className='game'><img alt={game.awayTeamId} className='logo'src={`/logos/${game.awayTeamId}.png`}/> <span className={scoreClass(game.awayScore, game.homeScore)}>
  {game.awayScore}
</span> @ <img alt={game.homeTeamId} className='logo'src={`/logos/${game.homeTeamId}.png`}/> <span className={scoreClass(game.homeScore, game.awayScore)}>
  {game.homeScore}
</span></div>

))}
    </div>
  )
}

export default App

