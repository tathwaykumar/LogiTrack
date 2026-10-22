import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../services/apiClient.js'
import { formatCurrency, formatNumber } from '../lib/format.js'
import ProductImage, { productImageSrc } from './ProductImage.jsx'
import { EmptyState, ErrorState, Icon, Notice, SearchField, stagger } from './ui.jsx'

const LOW_STOCK = 10
const SORTS = [
  { value: 'featured', label: 'Featured' },
  { value: 'price-asc', label: 'Price: low to high' },
  { value: 'price-desc', label: 'Price: high to low' },
  { value: 'stock', label: 'Most in stock' },
]

function Shop({ session, onAuthExpired, onNavigate }) {
  const [products, setProducts] = useState([])
  const [cart, setCart] = useState({})
  const [loading, setLoading] = useState(true)
  const [checkingOut, setCheckingOut] = useState(false)
  const [error, setError] = useState('')
  const [checkoutError, setCheckoutError] = useState('')
  const [receipt, setReceipt] = useState(null)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('ALL')
  const [sort, setSort] = useState('featured')
  const [shippingAddress, setShippingAddress] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [cartNotice, setCartNotice] = useState('')
  const [cartOpen, setCartOpen] = useState(false)
  const catalogRef = useRef(null)
  const receiptRef = useRef(null)

  const loadProducts = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiGet('/shop/products', session.accessToken)
      if (!Array.isArray(data)) throw new Error('Unexpected response from the Shop API.')
      setProducts(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err.message || 'Unable to load products.')
    } finally {
      setLoading(false)
    }
  }, [onAuthExpired, session.accessToken])

  useEffect(() => { loadProducts() }, [loadProducts, refreshKey])

  useEffect(() => {
    if (!cartNotice) return undefined
    const timeout = window.setTimeout(() => setCartNotice(''), 3500)
    return () => window.clearTimeout(timeout)
  }, [cartNotice])

  useEffect(() => {
    if (!cartOpen) return undefined
    const closeOnEscape = (event) => { if (event.key === 'Escape') setCartOpen(false) }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [cartOpen])

  useEffect(() => {
    if (receipt) receiptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [receipt])

  const categories = useMemo(() => ['ALL', ...new Set(products.map((product) => product.category).filter(Boolean))], [products])
  const categoryCounts = useMemo(() => products.reduce((counts, product) => ({ ...counts, [product.category]: (counts[product.category] ?? 0) + 1 }), {}), [products])
  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase()
    const matches = products.filter((product) => {
      const matchesCategory = category === 'ALL' || product.category === category
      const matchesSearch = !query || [product.product_name, product.description, product.category].some((value) => String(value ?? '').toLowerCase().includes(query))
      return matchesCategory && matchesSearch
    })
    const sorted = [...matches]
    if (sort === 'price-asc') sorted.sort((a, b) => Number(a.unit_price) - Number(b.unit_price))
    if (sort === 'price-desc') sorted.sort((a, b) => Number(b.unit_price) - Number(a.unit_price))
    if (sort === 'stock') sorted.sort((a, b) => Number(b.available_stock) - Number(a.available_stock))
    return sorted
  }, [category, products, search, sort])
  const cartItems = useMemo(() => products.filter((product) => cart[product.product_id] > 0).map((product) => ({ ...product, quantity: cart[product.product_id] })), [cart, products])
  const subtotal = cartItems.reduce((total, item) => total + Number(item.unit_price) * item.quantity, 0)
  const cartCount = cartItems.reduce((total, item) => total + item.quantity, 0)
  const totalStock = products.reduce((total, product) => total + (Number(product.available_stock) || 0), 0)
  const featured = useMemo(
    () => [...products].filter((product) => productImageSrc(product.product_name) && Number(product.available_stock) > 0).sort((a, b) => Number(b.unit_price) - Number(a.unit_price)).slice(0, 3),
    [products],
  )

  function addToCart(product) {
    setReceipt(null)
    setCheckoutError('')
    setCartNotice(`${product.product_name} added to your cart.`)
    setCart((current) => {
      const quantity = current[product.product_id] ?? 0
      if (quantity >= Number(product.available_stock)) return current
      return { ...current, [product.product_id]: quantity + 1 }
    })
  }

  function updateQuantity(product, value) {
    const quantity = Math.max(0, Math.min(Number(product.available_stock), Number(value) || 0))
    setReceipt(null)
    setCheckoutError('')
    setCart((current) => {
      const next = { ...current }
      if (quantity === 0) delete next[product.product_id]
      else next[product.product_id] = quantity
      return next
    })
  }

  function clearFilters() {
    setSearch('')
    setCategory('ALL')
  }

  async function checkout(event) {
    event.preventDefault()
    setCheckoutError('')
    setReceipt(null)
    if (!shippingAddress.trim()) {
      setCheckoutError('Enter the shipping address for this order.')
      return
    }
    if (cartItems.length === 0) return
    setCheckingOut(true)
    try {
      const data = await apiPost('/shop/checkout', {
        shipping_address: shippingAddress.trim(),
        items: cartItems.map((item) => ({ product_id: item.product_id, quantity: item.quantity })),
      }, session.accessToken)
      setReceipt(data)
      setCart({})
      setShippingAddress('')
      setCartOpen(false)
      setRefreshKey((key) => key + 1)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setCheckoutError(err.message || 'Unable to place your order.')
    } finally {
      setCheckingOut(false)
    }
  }

  return (
    <div className="space-y-10">
      <Hero
        loading={loading}
        productCount={products.length}
        categoryCount={categories.length - 1}
        totalStock={totalStock}
        featured={featured}
        cartCount={cartCount}
        onBrowse={() => catalogRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
        onOpenCart={() => setCartOpen(true)}
      />

      {receipt && <div ref={receiptRef} className="scroll-mt-24"><Receipt receipt={receipt} onClose={() => setReceipt(null)} onPay={onNavigate ? () => onNavigate('payments') : null} /></div>}

      <div ref={catalogRef} className="scroll-mt-20 grid gap-8 xl:grid-cols-[minmax(0,1fr)_23rem]">
        <section aria-labelledby="catalog-heading" className="min-w-0">
          <div className="z-10 -mx-4 border-b border-line bg-ivory/95 px-4 py-4 lg:sticky lg:top-16 sm:-mx-8 sm:px-8 xl:mx-0 xl:rounded-b-2xl xl:px-0">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-baseline gap-3">
                <h2 id="catalog-heading" className="font-display text-3xl font-semibold whitespace-nowrap">The catalog</h2>
                <p className="text-sm text-stone" aria-live="polite">{loading ? 'Loading…' : `${filteredProducts.length} of ${products.length} products`}</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <SearchField value={search} onChange={setSearch} placeholder="Search products…" label="Search products" className="sm:w-72" />
                <label className="relative">
                  <span className="sr-only">Sort products</span>
                  <select value={sort} onChange={(event) => setSort(event.target.value)} className="field cursor-pointer appearance-none rounded-full! pr-10">
                    {SORTS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                  <Icon name="arrowRight" className="pointer-events-none absolute top-1/2 right-4 size-4 -translate-y-1/2 rotate-90 text-stone" />
                </label>
              </div>
            </div>
            <div role="group" aria-label="Filter products by category" className="scrollbar-thin mt-3 flex gap-2 overflow-x-auto pb-1">
              {categories.map((item) => (
                <button key={item} type="button" aria-pressed={category === item} onClick={() => setCategory(item)} className="chip shrink-0">
                  {item === 'ALL' ? 'All products' : item}
                  <span className={`rounded-full px-1.5 text-[0.7rem] ${category === item ? 'bg-lime text-ink' : 'bg-cream text-stone'}`}>{item === 'ALL' ? products.length : categoryCounts[item] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6">
            {loading && products.length === 0 ? (
              <div className="grid gap-5 sm:grid-cols-2 2xl:grid-cols-3" aria-label="Loading products" aria-busy="true">
                {[1, 2, 3, 4, 5, 6].map((item) => <div key={item} className="space-y-3"><div className="skeleton aspect-[4/3.4] rounded-[1.6rem]!" /><div className="skeleton h-5 w-2/3" /><div className="skeleton h-4 w-1/3" /></div>)}
              </div>
            ) : error ? (
              <div className="panel"><ErrorState title="We couldn't load the catalog" message={error} onRetry={() => setRefreshKey((key) => key + 1)} /></div>
            ) : filteredProducts.length === 0 ? (
              <div className="panel">
                <EmptyState
                  icon="search"
                  title={products.length ? 'Nothing matches that search' : 'The shelves are empty'}
                  text={products.length ? 'Try a different product name or switch category.' : 'Products will appear here once warehouses list stock.'}
                  action={products.length > 0 && <button type="button" onClick={clearFilters} className="btn btn-ink">Clear filters</button>}
                />
              </div>
            ) : (
              <div className={`grid gap-x-5 gap-y-8 sm:grid-cols-2 2xl:grid-cols-3 transition-opacity ${loading ? 'opacity-60' : ''}`}>
                {filteredProducts.map((product, index) => (
                  <ProductCard key={product.product_id} index={index} product={product} cartQuantity={cart[product.product_id] ?? 0} onAdd={addToCart} onQuantityChange={updateQuantity} />
                ))}
              </div>
            )}
          </div>
        </section>

        {cartOpen && <button type="button" aria-label="Close cart" className="animate-fade fixed inset-0 z-40 bg-ink/50 xl:hidden" onClick={() => setCartOpen(false)} />}
        <div
          id="shop-cart"
          role={cartOpen ? 'dialog' : undefined}
          aria-modal={cartOpen ? 'true' : undefined}
          aria-label="Shopping cart"
          className={`fixed inset-y-0 right-0 z-50 w-full max-w-md transition-[transform,visibility] duration-300 ease-out xl:visible xl:static xl:z-auto xl:w-auto xl:max-w-none xl:translate-x-0 xl:transition-none ${cartOpen ? 'visible translate-x-0' : 'invisible translate-x-full'}`}
        >
          <CartPanel
            cartItems={cartItems}
            cartCount={cartCount}
            subtotal={subtotal}
            shippingAddress={shippingAddress}
            checkingOut={checkingOut}
            error={checkoutError}
            onAddressChange={setShippingAddress}
            onQuantityChange={updateQuantity}
            onCheckout={checkout}
            onClose={() => setCartOpen(false)}
          />
        </div>
      </div>

      <div aria-live="polite" className="pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 lg:left-[calc(50%+8.75rem)]">
        {cartNotice && (
          <div className="animate-rise flex items-center gap-3 rounded-full bg-ink py-2 pr-5 pl-2 text-sm font-semibold text-paper shadow-[var(--shadow-lift)]">
            <span className="grid size-7 place-items-center rounded-full bg-lime text-ink"><Icon name="check" className="size-4" strokeWidth={2.4} /></span>
            {cartNotice}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={() => setCartOpen(true)}
        aria-controls="shop-cart"
        aria-expanded={cartOpen}
        aria-label={`Open cart with ${cartCount} item${cartCount === 1 ? '' : 's'}`}
        className="fixed right-5 bottom-5 z-30 inline-flex items-center gap-3 rounded-full bg-ink py-2 pr-2 pl-5 text-sm font-semibold text-paper shadow-[var(--shadow-lift)] transition hover:-translate-y-0.5 xl:hidden"
      >
        <Icon name="cart" className="size-5 text-lime" />
        {formatCurrency(subtotal)}
        <span className="grid min-w-9 place-items-center rounded-full bg-lime px-2 py-1.5 text-ink">{cartCount}</span>
      </button>
    </div>
  )
}

function Hero({ loading, productCount, categoryCount, totalStock, featured, cartCount, onBrowse, onOpenCart }) {
  const [lead, ...rest] = featured
  return (
    <section className="animate-rise relative overflow-hidden rounded-[2rem] border border-line bg-paper shadow-[var(--shadow-card)]">
      <div className="grid lg:grid-cols-[1.05fr_0.95fr]">
        <div className="relative flex flex-col justify-between gap-10 p-7 sm:p-10 lg:p-12">
          <div>
            <p className="eyebrow inline-flex items-center gap-2 rounded-full bg-ink px-3 py-1.5 text-paper">
              <span className="size-1.5 animate-pulse rounded-full bg-lime" aria-hidden="true" />
              Stock synced live from our warehouses
            </p>
            <h1 className="font-display mt-6 text-[3.1rem] leading-[0.9] font-semibold sm:text-7xl xl:text-[5.4rem]">
              Tech essentials, <span className="font-serif-accent font-normal text-graphite">dispatched</span>{' '}
              <span className="relative inline-block">
                <span className="relative z-10">with intent.</span>
                <span className="absolute inset-x-0 bottom-[0.08em] z-0 h-[0.28em] -rotate-1 bg-lime" aria-hidden="true" />
              </span>
            </h1>
            <p className="mt-6 max-w-md text-base leading-7 text-stone">
              Every item ships from a LogiTrack warehouse and is tracked from checkout to your door.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button type="button" onClick={onBrowse} className="btn btn-ink px-6! py-3!">
                Browse the catalog <Icon name="arrowRight" className="size-4" />
              </button>
              <button type="button" onClick={onOpenCart} className="btn btn-outline px-6! py-3! xl:hidden">
                <Icon name="cart" className="size-4" /> Cart ({cartCount})
              </button>
            </div>
          </div>
          <dl className="grid grid-cols-3 gap-4 border-t border-line pt-6">
            {[
              ['Products', productCount],
              ['Categories', categoryCount],
              ['Units in stock', totalStock],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="eyebrow text-stone">{label}</dt>
                <dd className="mt-2 text-3xl font-semibold tracking-[-0.04em]">{loading && !productCount ? '—' : formatNumber(value)}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="on-dark relative min-h-[22rem] overflow-hidden bg-ink p-6 sm:p-8">
          <svg className="absolute inset-0 size-full text-paper/[0.07]" aria-hidden="true">
            <defs><pattern id="hero-grid" width="44" height="44" patternUnits="userSpaceOnUse"><path d="M44 0H0v44" fill="none" stroke="currentColor" /></pattern></defs>
            <rect width="100%" height="100%" fill="url(#hero-grid)" />
          </svg>
          <svg className="absolute inset-0 size-full" viewBox="0 0 400 400" preserveAspectRatio="none" aria-hidden="true">
            <path d="M20 360 C 140 330, 90 160, 220 170 S 330 60, 390 30" fill="none" stroke="#d4f53c" strokeWidth="2" strokeDasharray="6 10" style={{ animation: 'dash 2.4s linear infinite' }} />
          </svg>
          {lead ? (
            <div className="relative grid h-full min-h-[20rem] grid-cols-6 grid-rows-6 gap-3">
              <FeatureTile product={lead} className="col-span-4 row-span-6 sm:col-span-4" large />
              {rest.map((product, index) => (
                <FeatureTile key={product.product_id} product={product} className={`col-span-2 row-span-3 ${index === 1 ? 'translate-y-4' : ''}`} />
              ))}
            </div>
          ) : (
            <div className="relative grid h-full place-items-center">
              {loading ? <div className="h-64 w-full rounded-3xl bg-paper/10" /> : <p className="text-paper/60">Featured products appear when stock is available.</p>}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function FeatureTile({ product, className = '', large = false }) {
  return (
    <figure className={`group relative overflow-hidden rounded-[1.4rem] ring-1 ring-paper/10 ${className}`}>
      <ProductImage name={product.product_name} category={product.category} className="size-full" imgClassName="transition-transform duration-700 group-hover:scale-105" eager />
      {large ? (
        <figcaption className="absolute right-3 bottom-3 left-3 flex items-center justify-between gap-2 rounded-full bg-ink/90 py-1.5 pr-1.5 pl-4 text-paper">
          <span className="hidden truncate font-semibold sm:inline">{product.product_name}</span>
          <span className="shrink-0 rounded-full bg-lime px-2.5 py-0.5 font-semibold text-ink"><span className="sr-only sm:hidden">{product.product_name}, </span>{formatCurrency(product.unit_price)}</span>
        </figcaption>
      ) : (
        <figcaption className="absolute bottom-2 left-2 rounded-full bg-lime px-2 py-0.5 text-[0.7rem] font-bold text-ink">
          <span className="sr-only">{product.product_name}, </span>{formatCurrency(product.unit_price)}
        </figcaption>
      )}
    </figure>
  )
}

function StockLabel({ stock }) {
  const value = Number(stock)
  if (value <= 0) return <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-bad"><span className="size-1.5 rounded-full bg-bad" />Sold out</span>
  if (value <= LOW_STOCK) return <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-warn"><span className="size-1.5 rounded-full bg-warn" />Only {value} left</span>
  return <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ok"><span className="size-1.5 rounded-full bg-ok" />{formatNumber(value)} in stock</span>
}

function ProductCard({ product, cartQuantity, onAdd, onQuantityChange, index }) {
  const stock = Number(product.available_stock)
  const inStock = stock > 0
  const maxInCart = cartQuantity >= stock
  return (
    <article className="group animate-rise flex flex-col" style={stagger(Math.min(index, 8), 50)}>
      <div className="relative overflow-hidden rounded-[1.6rem] ring-1 ring-line transition-shadow duration-300 group-hover:shadow-[var(--shadow-lift)]">
        <ProductImage
          name={product.product_name}
          category={product.category}
          className="aspect-[4/3.4]"
          imgClassName={`transition-transform duration-700 ease-out group-hover:scale-[1.06] ${inStock ? '' : 'grayscale opacity-60'}`}
        />
        <span className="eyebrow absolute top-3 left-3 rounded-full bg-paper/95 px-2.5 py-1 text-ink">{product.category || 'Uncategorised'}</span>
        {cartQuantity > 0 && (
          <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded-full bg-lime px-2.5 py-1 text-xs font-bold text-ink">
            <Icon name="cart" className="size-3.5" strokeWidth={2.2} /> {cartQuantity}
          </span>
        )}
        {!inStock && <span className="font-display absolute inset-x-0 bottom-0 bg-ink/85 py-2 text-center text-sm font-semibold text-paper">Sold out — back soon</span>}
      </div>

      <div className="flex flex-1 flex-col px-1 pt-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-xl leading-tight font-semibold">{product.product_name}</h3>
          <p className="shrink-0 text-lg font-semibold tracking-tight">{formatCurrency(product.unit_price)}</p>
        </div>
        <p className="mt-1.5 line-clamp-2 flex-1 text-sm leading-6 text-stone">{product.description || 'No description available.'}</p>
        <div className="mt-4 flex items-center justify-between gap-3">
          <StockLabel stock={stock} />
          {cartQuantity > 0 ? (
            <QuantityStepper item={{ ...product, quantity: cartQuantity }} onQuantityChange={onQuantityChange} />
          ) : (
            <button type="button" onClick={() => onAdd(product)} disabled={!inStock || maxInCart} className="btn btn-ink py-2!" aria-label={`Add ${product.product_name} to cart`}>
              <Icon name="plus" className="size-4" strokeWidth={2.2} /> Add to cart
            </button>
          )}
        </div>
      </div>
    </article>
  )
}

function QuantityStepper({ item, onQuantityChange }) {
  const atMax = item.quantity >= Number(item.available_stock)
  return (
    <div className="inline-flex items-center rounded-full bg-ink p-1 text-paper">
      <button type="button" onClick={() => onQuantityChange(item, item.quantity - 1)} className="grid size-8 place-items-center rounded-full transition hover:bg-paper/15" aria-label={`Decrease ${item.product_name} quantity`}>
        <Icon name={item.quantity === 1 ? 'trash' : 'minus'} className="size-4" />
      </button>
      <span className="min-w-8 text-center text-sm font-bold tabular-nums" aria-live="polite">{item.quantity}</span>
      <button type="button" onClick={() => onQuantityChange(item, item.quantity + 1)} disabled={atMax} className="grid size-8 place-items-center rounded-full bg-lime text-ink transition hover:bg-lime-deep disabled:cursor-not-allowed disabled:opacity-40" aria-label={`Increase ${item.product_name} quantity`}>
        <Icon name="plus" className="size-4" strokeWidth={2.2} />
      </button>
    </div>
  )
}

function CartPanel({ cartItems, cartCount, subtotal, shippingAddress, checkingOut, error, onAddressChange, onQuantityChange, onCheckout, onClose }) {
  return (
    <aside className="flex h-full flex-col overflow-hidden bg-paper shadow-[var(--shadow-lift)] xl:sticky xl:top-24 xl:h-auto xl:max-h-[calc(100vh-7rem)] xl:rounded-[1.8rem] xl:border xl:border-line xl:shadow-[var(--shadow-card)]">
      <div className="on-dark flex items-center justify-between bg-ink px-6 py-5 text-paper">
        <div>
          <p className="eyebrow text-paper/50">Your cart</p>
          <h2 className="font-display mt-1 text-2xl font-semibold">{cartCount} item{cartCount === 1 ? '' : 's'}</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="grid size-11 place-items-center rounded-full bg-lime text-ink"><Icon name="cart" className="size-5" /></span>
          <button type="button" onClick={onClose} className="grid size-10 place-items-center rounded-full text-paper/70 hover:bg-paper/10 xl:hidden" aria-label="Close cart"><Icon name="x" className="size-5" /></button>
        </div>
      </div>

      {cartItems.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center px-8 py-14 text-center">
          <div className="relative">
            <span className="grid size-20 place-items-center rounded-full bg-cream"><Icon name="shop" className="size-8" strokeWidth={1.4} /></span>
            <span className="absolute -top-1 -right-1 size-5 rounded-full bg-lime ring-4 ring-paper" />
          </div>
          <p className="font-display mt-5 text-xl font-semibold">Your cart is empty</p>
          <p className="mt-2 text-sm leading-6 text-stone">Add an in-stock product to start an order.</p>
        </div>
      ) : (
        <form className="flex min-h-0 flex-1 flex-col" onSubmit={onCheckout}>
          <ul className="scrollbar-thin min-h-0 flex-1 divide-y divide-line overflow-y-auto px-6">
            {cartItems.map((item) => (
              <li key={item.product_id} className="flex gap-4 py-4">
                <ProductImage name={item.product_name} category={item.category} className="size-20 shrink-0 rounded-2xl" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold leading-tight">{item.product_name}</p>
                    <p className="text-sm font-semibold whitespace-nowrap">{formatCurrency(Number(item.unit_price) * item.quantity)}</p>
                  </div>
                  <p className="mt-0.5 text-xs text-stone">{formatCurrency(item.unit_price)} each · {formatNumber(item.available_stock)} available</p>
                  <div className="mt-2.5 flex items-center justify-between">
                    <QuantityStepper item={item} onQuantityChange={onQuantityChange} />
                    <button type="button" onClick={() => onQuantityChange(item, 0)} className="text-xs font-semibold text-stone underline-offset-4 hover:text-bad hover:underline">Remove</button>
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <div className="space-y-4 border-t border-line bg-ivory/60 px-6 py-5">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium text-stone">Subtotal</span>
              <span className="text-2xl font-semibold tracking-[-0.03em]">{formatCurrency(subtotal)}</span>
            </div>
            <p className="text-xs leading-5 text-stone">The final amount is recalculated from current prices at checkout. Payment is not collected at this step.</p>
            <label className="block">
              <span className="field-label">Shipping address</span>
              <textarea required value={shippingAddress} onChange={(event) => onAddressChange(event.target.value)} maxLength="255" rows="2" placeholder="House, street, city" className="field resize-y" />
            </label>
            {error && <Notice tone="error">{error}</Notice>}
            <button type="submit" disabled={checkingOut} className="btn btn-lime w-full justify-between! px-5! py-3.5! text-base!">
              <span>{checkingOut ? 'Placing order…' : 'Place order'}</span>
              <span className="inline-flex items-center gap-2">{formatCurrency(subtotal)} <Icon name="arrowRight" className="size-4" /></span>
            </button>
          </div>
        </form>
      )}
    </aside>
  )
}

function Receipt({ receipt, onClose, onPay }) {
  const order = receipt.order ?? {}
  const invoice = receipt.invoice ?? {}
  return (
    <section role="status" className="animate-rise on-dark relative overflow-hidden rounded-[2rem] bg-ink p-6 text-paper sm:p-9">
      <span className="absolute -top-16 -right-16 size-56 rounded-full bg-lime/15" aria-hidden="true" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-4">
          <span className="grid size-14 shrink-0 place-items-center rounded-full bg-lime text-ink"><Icon name="check" className="size-7" strokeWidth={2.4} /></span>
          <div>
            <p className="eyebrow text-lime">Order confirmed</p>
            <h2 className="font-display mt-1 text-3xl font-semibold sm:text-4xl">Order #{order.order_id} is in.</h2>
            <p className="mt-2 max-w-xl text-paper/70">Invoice #{invoice.invoice_id} has been issued for {formatCurrency(invoice.total_amount)}. Payment is still pending.</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {onPay && <button type="button" onClick={onPay} className="btn btn-lime">Go to payments <Icon name="arrowRight" className="size-4" /></button>}
          <button type="button" onClick={onClose} className="btn bg-paper/10 text-paper hover:bg-paper/20">Dismiss</button>
        </div>
      </div>
      <dl className="relative mt-8 grid gap-4 border-t border-paper/10 pt-6 text-sm sm:grid-cols-4">
        <div><dt className="eyebrow text-paper/50">Order status</dt><dd className="mt-1.5 font-semibold">{order.order_status}</dd></div>
        <div><dt className="eyebrow text-paper/50">Invoice status</dt><dd className="mt-1.5 font-semibold">{invoice.invoice_status}</dd></div>
        <div><dt className="eyebrow text-paper/50">Items</dt><dd className="mt-1.5 font-semibold">{(order.items ?? []).reduce((sum, item) => sum + Number(item.quantity || 0), 0)}</dd></div>
        <div><dt className="eyebrow text-paper/50">Shipping to</dt><dd className="mt-1.5 font-semibold">{order.shipping_address}</dd></div>
      </dl>
    </section>
  )
}

export default Shop
