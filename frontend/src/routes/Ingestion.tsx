import { Activity, FileJson, Upload } from 'lucide-react'
import type { HealthSummary, StreamingStatus } from '../services/api'

export function IngestionRoute({
  fileIngestionLoading,
  ingestJsonPayload,
  ingestSelectedFile,
  ingestSourceType,
  ingestTitle,
  ingestionMessage,
  jsonIngestionLoading,
  jsonMode,
  jsonPayload,
  selectedEquipment,
  selectedHealth,
  setIngestFile,
  setIngestSourceType,
  setIngestTitle,
  setJsonMode,
  setJsonPayload,
  streamingStatus,
}: {
  fileIngestionLoading: boolean
  ingestJsonPayload: () => void
  ingestSelectedFile: () => void
  ingestSourceType: string
  ingestTitle: string
  ingestionMessage: string
  jsonIngestionLoading: boolean
  jsonMode: 'documents' | 'records'
  jsonPayload: string
  selectedEquipment: string
  selectedHealth?: HealthSummary
  setIngestFile: (file: File | null) => void
  setIngestSourceType: (value: string) => void
  setIngestTitle: (value: string) => void
  setJsonMode: (value: 'documents' | 'records') => void
  setJsonPayload: (value: string) => void
  streamingStatus: StreamingStatus | null
}) {
  return (
    <section className="detailPanel ingestionView">
      <div className="sectionHeader">
        <Upload size={18} />
        <h2>Ingestion</h2>
      </div>
      <div className="ingestionContext">
        <span>Target asset</span>
        <strong>{selectedHealth?.equipment.name}</strong>
        <small>{selectedEquipment}</small>
      </div>
      <div className="streamingStatusPanel">
        <div className="sectionHeader compactHeader">
          <Activity size={18} />
          <h3>IoT Stream</h3>
        </div>
        <div className="streamingStatusGrid">
          <span>State</span>
          <strong className={`streamState ${streamingStatus?.state ?? 'error'}`}>{streamingStatus?.state ?? 'unavailable'}</strong>
          <span>Broker</span>
          <strong>{streamingStatus?.broker ?? 'nats'}</strong>
          <span>Stream</span>
          <strong>{streamingStatus?.stream ?? 'MW_IOT'}</strong>
          <span>Consumer</span>
          <strong>{streamingStatus?.consumer ?? 'maintenance-wizard-ingestor'}</strong>
          <span>Processed</span>
          <strong>{streamingStatus?.processed_count ?? 0}</strong>
          <span>Failed</span>
          <strong>{streamingStatus?.failed_count ?? 0}</strong>
          <span>Last Message</span>
          <strong>{streamingStatus?.last_message_timestamp ?? 'None yet'}</strong>
        </div>
        {streamingStatus?.last_error && <p className="inlineStatus errorText">{streamingStatus.last_error}</p>}
      </div>
      <div className="ingestionGrid">
        <label className="field">
          <span>Source</span>
          <select value={ingestSourceType} onChange={(event) => setIngestSourceType(event.target.value)}>
            <option value="manual">Manual</option>
            <option value="sop">SOP</option>
            <option value="log">Log</option>
            <option value="alert">Alert</option>
            <option value="spares">Spares</option>
            <option value="history">History</option>
          </select>
        </label>
        <label className="field">
          <span>Title</span>
          <input value={ingestTitle} onChange={(event) => setIngestTitle(event.target.value)} />
        </label>
        <label className="field fileField">
          <span>File</span>
          <input
            aria-label="Ingestion file"
            type="file"
            accept=".txt,.md,.markdown,.csv,.log,.json,.pdf,text/*,application/pdf"
            onChange={(event) => setIngestFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button onClick={ingestSelectedFile} disabled={fileIngestionLoading} title="Upload maintenance document">
          {fileIngestionLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Upload size={16} />}
          {fileIngestionLoading ? 'Uploading...' : 'Upload'}
        </button>
      </div>
      <div className="jsonIngest">
        <label className="field">
          <span>Payload</span>
          <select value={jsonMode} onChange={(event) => setJsonMode(event.target.value as 'documents' | 'records')}>
            <option value="documents">Documents</option>
            <option value="records">Records</option>
          </select>
        </label>
        <textarea
          aria-label="Ingestion JSON"
          value={jsonPayload}
          onChange={(event) => setJsonPayload(event.target.value)}
          placeholder={jsonMode === 'documents' ? '{"documents":[...]}' : '{"alerts":[...],"sensor_readings":[...]}'}
        />
        <button className="textButton" onClick={ingestJsonPayload} disabled={jsonIngestionLoading}>
          {jsonIngestionLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <FileJson size={16} />}
          {jsonIngestionLoading ? 'Importing...' : 'Import JSON'}
        </button>
      </div>
      {ingestionMessage && <p className="inlineStatus">{ingestionMessage}</p>}
    </section>
  )
}
