import { describe, expect, it } from 'vitest'
import { emptyLearningRefreshMessage, learningJudgeProgressMessage, learningRefreshMessage } from './appModel'

describe('learning status copy', () => {
  it('explains when refreshing learning examples finds no training sources', () => {
    expect(learningRefreshMessage(0)).toBe(emptyLearningRefreshMessage)
  })

  it('summarizes refreshed learning examples with singular and plural grammar', () => {
    expect(learningRefreshMessage(1)).toBe('Refreshed 1 learning example')
    expect(learningRefreshMessage(2)).toBe('Refreshed 2 learning examples')
  })

  it('formats learning judge progress from source types', () => {
    expect(learningJudgeProgressMessage('feedback')).toBe(
      'Judging feedback example. Live LLM checks can take up to 15 seconds before falling back.',
    )
    expect(learningJudgeProgressMessage('assistant_interaction')).toBe(
      'Judging assistant interaction example. Live LLM checks can take up to 15 seconds before falling back.',
    )
  })
})
