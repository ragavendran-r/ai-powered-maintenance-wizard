import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { IngestionRoute } from './Ingestion'

function renderMockedIngestion(overrides: Record<string, unknown> = {}) {
  const props = {
    fileIngestionLoading: false,
    ingestJsonPayload: vi.fn(),
    ingestSelectedFile: vi.fn(),
    ingestSourceType: 'sop',
    ingestTitle: '',
    jsonIngestionLoading: false,
    jsonMode: 'documents',
    jsonPayload: '',
    selectedEquipment: 'RM-DRIVE-01',
    selectedHealth: {
      equipment: {
        id: 'RM-DRIVE-01',
        name: 'Hot Strip Mill Main Drive Motor',
        area: 'Hot Rolling Mill',
        process: 'Finishing stand drive',
        criticality: 5,
        status: 'degraded',
      },
      risk_level: 'critical',
      health_score: 0,
      active_alerts: [],
      anomalies: [],
      top_spares_constraints: [],
      notes: [],
    },
    setIngestFile: vi.fn(),
    setIngestSourceType: vi.fn(),
    setIngestTitle: vi.fn(),
    setJsonMode: vi.fn(),
    setJsonPayload: vi.fn(),
    streamingStatus: {
      enabled: true,
      state: 'running',
      broker: 'nats',
      stream: 'MW_IOT',
      consumer: 'maintenance-wizard-ingestor',
      processed_count: 7,
      failed_count: 1,
      last_message_timestamp: '2026-06-18T10:00:00+05:30',
      last_error: null,
    },
    ...overrides,
  }
  render(<IngestionRoute {...props} />)
  return props
}

afterEach(() => cleanup())

it('shows selected asset and IoT stream status', () => {
  renderMockedIngestion()

  expect(screen.getByRole('heading', { name: 'Ingestion' })).toBeInTheDocument()
  expect(screen.getByText('Hot Strip Mill Main Drive Motor')).toBeInTheDocument()
  expect(screen.getByText('RM-DRIVE-01')).toBeInTheDocument()
  expect(screen.getByText('running')).toBeInTheDocument()
  expect(screen.getByText('MW_IOT')).toBeInTheDocument()
  expect(screen.getByText('maintenance-wizard-ingestor')).toBeInTheDocument()
})

it('routes file source, title, file selection, and upload through callbacks', () => {
  const props = renderMockedIngestion()

  fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'manual' } })
  expect(props.setIngestSourceType).toHaveBeenCalledWith('manual')

  fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Uploaded SOP' } })
  expect(props.setIngestTitle).toHaveBeenCalledWith('Uploaded SOP')

  const file = new File(['Inspect bearing housing when vibration increases.'], 'uploaded_sop.txt', { type: 'text/plain' })
  fireEvent.change(screen.getByLabelText('Ingestion file'), { target: { files: [file] } })
  expect(props.setIngestFile).toHaveBeenCalledWith(file)

  fireEvent.click(screen.getByRole('button', { name: 'Upload' }))
  expect(props.ingestSelectedFile).toHaveBeenCalled()
})

it('shows upload loading state without waiting for app-level network timers', () => {
  renderMockedIngestion({ fileIngestionLoading: true })

  expect(screen.getByRole('button', { name: /uploading/i })).toBeDisabled()
})

it('routes JSON payload mode, text, and import through callbacks', () => {
  const props = renderMockedIngestion()

  fireEvent.change(screen.getByLabelText('Payload'), { target: { value: 'records' } })
  expect(props.setJsonMode).toHaveBeenCalledWith('records')

  const payload = '{"documents":[{"id":"DOC-UI","source_type":"sop","equipment_id":"RM-DRIVE-01","title":"UI SOP","content":"Check vibration."}]}'
  fireEvent.change(screen.getByLabelText('Ingestion JSON'), { target: { value: payload } })
  expect(props.setJsonPayload).toHaveBeenCalledWith(payload)

  fireEvent.click(screen.getByRole('button', { name: 'Import JSON' }))
  expect(props.ingestJsonPayload).toHaveBeenCalled()
})

it('shows JSON import loading state without waiting for app-level network timers', () => {
  renderMockedIngestion({ jsonIngestionLoading: true })

  expect(screen.getByRole('button', { name: /importing/i })).toBeDisabled()
})
