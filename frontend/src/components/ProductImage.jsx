import { useState } from 'react'

// Local studio photographs in public/images/products, keyed by catalog product name.
// They were cut from the repository's shop-catalog-sprite.png (one cell per product).
const PRODUCT_IMAGES = {
  'laptop': 'laptop',
  'wireless mouse': 'wireless-mouse',
  'mechanical keyboard': 'mechanical-keyboard',
  'monitor': 'monitor',
  'usb-c hub': 'usb-c-hub',
  'headphones': 'headphones',
  'webcam': 'webcam',
  'external ssd': 'external-ssd',
  'smartphone': 'smartphone',
  'portable power bank': 'portable-power-bank',
  'ergonomic laptop stand': 'ergonomic-laptop-stand',
  'bluetooth speaker': 'bluetooth-speaker',
}

export function productImageSrc(name) {
  const slug = PRODUCT_IMAGES[String(name ?? '').trim().toLowerCase()]
  return slug ? `/images/products/${slug}.webp` : null
}

const CATEGORY_GLYPHS = {
  electronics: 'M5 6h14v9H5zM3 18h18M9 15v3M15 15v3',
  accessories: 'M8 4h8v16H8zM11 17h2M5 8v8M19 8v8',
  storage: 'M5 5h14v14H5zM8 8h8v4H8zM15 16h.01',
}

/** Category illustration used when a product has no photo or its photo fails to load. */
function ProductFallback({ name, category }) {
  const glyph = CATEGORY_GLYPHS[String(category ?? '').toLowerCase()] ?? 'm4 7.5 8-4.5 8 4.5v9L12 21l-8-4.5zM4 7.5l8 4.5 8-4.5M12 12v9'
  return (
    <div className="relative grid size-full place-items-center overflow-hidden bg-cream" role="img" aria-label={`${name ?? 'Product'} illustration`}>
      <span className="absolute -right-6 -bottom-6 size-24 rounded-full bg-lime/70" aria-hidden="true" />
      <svg viewBox="0 0 24 24" className="relative size-1/3 text-ink" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={glyph} />
      </svg>
      <span className="eyebrow absolute top-3 left-3 text-stone">{category || 'Product'}</span>
    </div>
  )
}

/**
 * A product photograph in a fixed-ratio studio frame. object-contain keeps the
 * whole product visible; the frame colour matches the photographs' backdrop.
 */
export default function ProductImage({ name, category, className = 'aspect-square', imgClassName = '', eager = false }) {
  const src = productImageSrc(name)
  const [failed, setFailed] = useState(false)

  return (
    <div className={`relative overflow-hidden bg-studio ${className}`}>
      {src && !failed ? (
        <img
          src={src}
          alt={name}
          width="356"
          height="356"
          loading={eager ? 'eager' : 'lazy'}
          decoding="async"
          onError={() => setFailed(true)}
          className={`size-full object-contain ${imgClassName}`}
        />
      ) : (
        <ProductFallback name={name} category={category} />
      )}
    </div>
  )
}
