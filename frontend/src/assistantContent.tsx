import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { formatWorkOrderStatusText } from './workOrderStatus'

export type AssistantTurn = {
  id: string
  role: 'user' | 'assistant'
  content: string
  details?: string[]
  provider?: string
  usedLiveProvider?: boolean
  runtimeFallback?: boolean
  runtimeFallbackReason?: string | null
}

export function assistantTurnId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function assistantProviderLabel(turn: AssistantTurn) {
  if (!turn.provider) return ''
  if (turn.provider === 'deterministic') return 'Dashboard data'
  if (turn.provider === 'grounded_priority_guard') return 'Dashboard data'
  if (turn.provider === 'work_order_tool') return 'Trinity action'
  if (turn.runtimeFallback || turn.provider === 'fallback') return `LLM error · ${turn.provider}`
  return `${turn.usedLiveProvider ? 'Live LLM' : 'LLM error'} · ${turn.provider}`
}

export function AssistantMessageContent({ turn }: { turn: AssistantTurn }) {
  if (turn.role === 'assistant') {
    return <FormattedAssistantContent content={normalizeAssistantChatMarkdown(turn.content)} />
  }
  return <p>{turn.content}</p>
}

export function scrollStreamToBottom(ref: { current: HTMLElement | null }) {
  const scroll = () => {
    const node = ref.current
    if (!node) return
    node.scrollTop = node.scrollHeight
    if (typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'end', inline: 'nearest', behavior: 'auto' })
      node.scrollTop = node.scrollHeight
    }
  }

  scroll()

  if (typeof window !== 'undefined' && window.requestAnimationFrame) {
    window.requestAnimationFrame(scroll)
    window.setTimeout(scroll, 0)
    window.setTimeout(scroll, 50)
    window.setTimeout(scroll, 150)
    window.setTimeout(scroll, 300)
    return
  }

  scroll()
}

export function usePinnedStreamScroll(ref: { current: HTMLElement | null }, trigger: string) {
  useEffect(() => {
    const node = ref.current
    if (!node) return

    scrollStreamToBottom(ref)

    if (typeof MutationObserver === 'undefined') return

    const observer = new MutationObserver(() => scrollStreamToBottom(ref))
    observer.observe(node, {
      childList: true,
      characterData: true,
      subtree: true,
    })

    return () => observer.disconnect()
  }, [ref, trigger])
}

type AssistantContentBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'ol' | 'ul'; items: string[] }

export function FormattedAssistantContent({ content }: { content: string }) {
  const blocks = parseAssistantContent(formatWorkOrderStatusText(content))
  return (
    <div className="assistantFormattedContent">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const HeadingTag = block.level >= 4 ? 'h4' : 'h3'
          return <HeadingTag key={`heading-${index}`}>{renderInlineMarkdown(block.text, `heading-${index}`)}</HeadingTag>
        }
        if (block.type === 'ol') {
          return (
            <ol key={`ol-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item, `ol-${index}-${itemIndex}`)}</li>
              ))}
            </ol>
          )
        }
        if (block.type === 'ul') {
          return (
            <ul key={`ul-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item, `ul-${index}-${itemIndex}`)}</li>
              ))}
            </ul>
          )
        }
        if (block.type === 'paragraph') {
          return <p key={`paragraph-${index}`}>{renderInlineMarkdown(block.text, `paragraph-${index}`)}</p>
        }
        return null
      })}
    </div>
  )
}

export function normalizePmDraftMarkdown(content: string) {
  const sectionHeadings = new Set([
    'PM Plan',
    'Trigger',
    'Monitoring Thresholds',
    'Generated Task List',
    'Spares Strategy',
    'Adjustment Notes',
    'Smith Execution Steps',
  ])
  const listSections = new Set([
    'Trigger',
    'Monitoring Thresholds',
    'Generated Task List',
    'Spares Strategy',
    'Adjustment Notes',
    'Smith Execution Steps',
  ])
  const lines = content
    .replace(/\r\n/g, '\n')
    .replace(/(#{1,4}\s+[^\n]+?)(?=#{1,4}\s+)/g, '$1\n')
    .replace(/([^\n])###\s+/g, '$1\n### ')
    .split('\n')
  const normalized: string[] = []
  let activeSection = ''

  lines.forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      normalized.push('')
      return
    }

    const markdownHeading = trimmed.match(/^#{1,4}\s+(.+)$/)
    if (markdownHeading) {
      const heading = stripMarkdownHeadingSuffix(markdownHeading[1]).replace(/:$/, '').trim()
      activeSection = sectionHeadings.has(heading) ? heading : activeSection
      normalized.push(`### ${heading}`)
      return
    }

    const labelHeading = trimmed.match(/^([A-Za-z][A-Za-z ]+):\s*(.*)$/)
    if (labelHeading && sectionHeadings.has(labelHeading[1].trim())) {
      activeSection = labelHeading[1].trim()
      normalized.push(`### ${activeSection}`)
      if (labelHeading[2].trim()) {
        normalized.push(normalizePmDraftListLine(labelHeading[2].trim(), activeSection, listSections))
      }
      return
    }

    if (sectionHeadings.has(trimmed.replace(/:$/, ''))) {
      activeSection = trimmed.replace(/:$/, '')
      normalized.push(`### ${activeSection}`)
      return
    }

    normalized.push(normalizePmDraftListLine(trimmed, activeSection, listSections))
  })

  return normalized.join('\n').replace(/\n{3,}/g, '\n\n').trimStart()
}

function normalizePmDraftListLine(line: string, activeSection: string, listSections: Set<string>) {
  if (/^[-*]\s+/.test(line) || /^\d+[.)]\s+/.test(line)) return line
  if (listSections.has(activeSection)) return `- ${line}`
  return line
}

function parseAssistantContent(content: string): AssistantContentBlock[] {
  const normalized = normalizeAssistantContent(content)
  const blocks: AssistantContentBlock[] = []
  let listType: 'ol' | 'ul' | null = null
  let listItems: string[] = []

  function flushList() {
    if (listType && listItems.length > 0) {
      blocks.push({ type: listType, items: listItems })
    }
    listType = null
    listItems = []
  }

  normalized.split('\n').forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      return
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushList()
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        text: stripMarkdownHeadingSuffix(heading[2]),
      })
      return
    }

    const ordered = trimmed.match(/^\d+\.\s+(.+)$/)
    if (ordered) {
      if (listType !== 'ol') flushList()
      listType = 'ol'
      listItems.push(ordered[1])
      return
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    if (unordered) {
      if (listType !== 'ul') flushList()
      listType = 'ul'
      listItems.push(unordered[1])
      return
    }

    flushList()
    blocks.push({ type: 'paragraph', text: trimmed })
  })

  flushList()
  return blocks.length > 0 ? blocks : [{ type: 'paragraph', text: content }]
}

function normalizeAssistantContent(content: string) {
  return content
    .replace(/\r\n/g, '\n')
    .replace(/\s+(#{1,4}\s+)/g, '\n$1')
    .replace(/(#{1,4}\s+[^:\n]+:)\s+(\d+\.\s+)/g, '$1\n$2')
    .replace(/\s+(\d+\.\s+(?:\*\*|[A-Z]))/g, '\n$1')
    .replace(/(?<!\*)\s+-\s+(?=[A-Z*])/g, '\n- ')
}

function normalizeAssistantChatMarkdown(content: string) {
  return content
    .split('\n')
    .map((line) => line.replace(/^\s*\*\*(.+?)\*\*\s*$/, '$1'))
    .join('\n')
}

function stripMarkdownHeadingSuffix(text: string) {
  return text.replace(/\s+#+$/, '')
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-strong-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${keyPrefix}-text-${index}`}>{part}</span>
  })
}
