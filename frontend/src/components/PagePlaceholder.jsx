import { formatLabel } from '../lib/format.js'
import { EmptyState, PageHeader } from './ui.jsx'

const COPY = { dashboard: 'A concise view of the activity that matters most to your operation.', orders: 'Create, review, and manage customer orders from one place.', shipments: 'Monitor shipment progress and keep teams aligned.', tracking: 'Follow every milestone from dispatch through delivery.', deliveries: 'Coordinate delivery work and completion status.', vehicles: 'Manage fleet availability, maintenance, and assignments.', drivers: 'Review driver availability and delivery responsibilities.', payments: 'Review payment status and transaction activity.', invoices: 'Manage billing records and invoice status.', analytics: 'Turn logistics activity into operational insight.', users: 'Manage access and roles across your organization.' }

function PagePlaceholder({ page, roleName }) {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={`${formatLabel(roleName)} workspace`} title={page.label} description={COPY[page.id]} />
      <div className="panel"><EmptyState icon="sparkle" title={`${page.label} features are coming next.`} text="This protected placeholder confirms the role-aware application shell is ready." /></div>
    </div>
  )
}

export default PagePlaceholder
