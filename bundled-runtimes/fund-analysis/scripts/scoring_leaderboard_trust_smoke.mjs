import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const scoringRoute = readFileSync(join(root, 'backend/routes/scoring.py'), 'utf8')

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, expected, label) {
  if (content.includes(expected)) {
    throw new Error(`${label} must not include text: ${expected}`)
  }
}

const leaderboardStart = scoringRoute.indexOf('@router.get("/leaderboard")')
const rulesStart = scoringRoute.indexOf('@router.get("/rules")')
if (leaderboardStart < 0 || rulesStart < 0 || rulesStart <= leaderboardStart) {
  throw new Error('scoring leaderboard route block not found')
}
const leaderboardBlock = scoringRoute.slice(leaderboardStart, rulesStart)

assertNotIncludes(leaderboardBlock, 'mock', 'scoring leaderboard trust')
assertNotIncludes(leaderboardBlock, 'get_fund_list', 'scoring leaderboard must not rank arbitrary provider page')
assertNotIncludes(leaderboardBlock, 'score_fund(perf, risk, style)', 'scoring leaderboard must not rebuild ad-hoc scores from provider page')
assertIncludes(leaderboardBlock, 'get_fund_repo().list_funds', 'scoring leaderboard database source')
assertIncludes(leaderboardBlock, 'sort_by=sort_by', 'scoring leaderboard database-side sort')
assertIncludes(leaderboardBlock, 'tradable_only=True', 'scoring leaderboard tradability gate')
assertIncludes(leaderboardBlock, '"ranking_source": "database"', 'scoring leaderboard source disclosure')
assertIncludes(leaderboardBlock, '"scoring_source": "database_screening_score_v1"', 'scoring leaderboard scoring disclosure')
assertIncludes(leaderboardBlock, '"data_source": "database"', 'scoring leaderboard data source disclosure')
assertIncludes(leaderboardBlock, 'target_type != "fund"', 'scoring leaderboard fund research scope')

console.log('OK scoring leaderboard uses database-ranked, source-disclosed fund research data')
