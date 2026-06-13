import { Activity } from 'lucide-react'
import type { AssetListItem } from '../services/api'
import { AssetsTable } from '../sharedComponents'

export function AssetsRoute({
  assetMessage,
  assets,
  onOpenAsset,
}: {
  assetMessage: string
  assets: AssetListItem[]
  onOpenAsset: (assetId: string) => void
}) {
  return (
    <section className="detailPanel assetsView">
      <div className="sectionHeader">
        <Activity size={18} />
        <h2>Assets</h2>
      </div>
      {assets.length > 0 ? (
        <AssetsTable assets={assets} onOpen={onOpenAsset} />
      ) : (
        <p className="emptyState">Asset table data is unavailable until the backend API responds.</p>
      )}
      {assetMessage && <p className="inlineStatus">{assetMessage}</p>}
    </section>
  )
}
