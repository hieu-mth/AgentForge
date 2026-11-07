import { useEffect, useMemo, useState } from 'react';
import { CATEGORIES, PRODUCTS } from './catalog.js';
import { cartTotals, changeCart, currency, listProducts, removeFromCart } from './store.js';

const KNOWN=new Set(PRODUCTS.map(x=>x.id));
const categoryName=id=>CATEGORIES.find(c=>c.id===id)?.name||'Sản phẩm';
const display=product=><span className={'product-illustration tone-'+product.tone} aria-hidden="true">
  <span className="illustration-ring"/><span className="product-glyph">{product.icon}</span>
</span>;

function ProductCard({product,onInspect,onAdd}) {
  return <article className="product-card">
    <button type="button" className="product-image-button" onClick={()=>onInspect(product)}
      aria-label={'Xem chi tiết '+product.name}>
      {display(product)}
      <span className="product-tag">{product.tag}</span>
    </button>
    <div className="product-description">
      <span className="product-category">{categoryName(product.category)}</span>
      <button className="text-button product-title" onClick={()=>onInspect(product)}>{product.name}</button>
      <div className="price-row"><strong>{currency(product.price)}</strong><span>Giá demo</span></div>
      <button className="add-button" onClick={()=>onAdd(product.id)}
        aria-label={'Thêm '+product.name+' vào giỏ demo'}>+ Thêm vào giỏ</button>
    </div>
  </article>;
}

export default function App() {
  const [search,setSearch]=useState('');
  const [category,setCategory]=useState('all');
  const [sort,setSort]=useState('featured');
  const [cart,setCart]=useState({});
  const [cartOpen,setCartOpen]=useState(false);
  const [selected,setSelected]=useState(null);
  const [toast,setToast]=useState('');
  const visible=useMemo(()=>listProducts(PRODUCTS,{search,category,sort}),[search,category,sort]);
  const totals=useMemo(()=>cartTotals(cart,PRODUCTS),[cart]);
  const cartProducts=PRODUCTS.filter(p=>cart[p.id]>0);
  const add=id=>{
    setCart(prev=>changeCart(prev,id,1,KNOWN));
    setToast('Đã thêm sản phẩm vào giỏ hàng demo');
  };
  useEffect(()=>{
    if(!toast)return;
    const handle=setTimeout(()=>setToast(''),2600);
    return ()=>clearTimeout(handle);
  },[toast]);
  useEffect(()=>{
    const handler=e=>{
      if(e.key==='Escape'){setSelected(null);setCartOpen(false);}
    };
    document.addEventListener('keydown',handler);
    return ()=>document.removeEventListener('keydown',handler);
  },[]);
  const reset=()=>{setSearch('');setCategory('all');setSort('featured');};
  const selectCategory=id=>{
    setCategory(id);
    document.getElementById('products')?.scrollIntoView({behavior:'smooth'});
  };
  return <div className="app-shell">
    <div className="utility-bar">
      <div className="site-container utility-inner">
        <span>✦ Marketplace thử nghiệm · Dữ liệu minh họa</span>
        <span>Không nhận thanh toán hoặc đơn hàng thật</span>
      </div>
    </div>
    <header className="site-header">
      <div className="site-container header-inner">
        <a className="logo" href="#top" aria-label="NovaMart - về đầu trang">
          <span className="logo-mark">n<span>✦</span></span><span>nova<span className="logo-tail">mart</span></span>
        </a>
        <label className="header-search"><span aria-hidden="true" className="search-symbol">⌕</span>
          <span className="sr-only">Tìm kiếm sản phẩm</span>
          <input value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="Tìm sản phẩm yêu thích..." type="search"/>
          <a href="#products" className="search-action">Tìm kiếm</a>
        </label>
        <button className="cart-trigger" onClick={()=>setCartOpen(true)}
          aria-label={'Mở giỏ hàng demo, '+totals.items+' sản phẩm'}>
          <span aria-hidden="true" className="cart-symbol">♙</span>
          <span>Giỏ hàng</span><span className="cart-counter">{totals.items}</span>
        </button>
      </div>
      <div className="site-container quick-trends">
        <span>Gợi ý:</span><button onClick={()=>setSearch('Áo khoác')}>Áo khoác</button>
        <button onClick={()=>setSearch('Tai nghe')}>Tai nghe</button>
        <button onClick={()=>setSearch('Gối')}>Gối</button>
      </div>
    </header>
    <main id="top">
      <section className="site-container hero-area" aria-label="Giới thiệu NovaMart">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-dot"/> NOVAMART COLLECTION 2026</div>
          <h1>Chạm vào điều <em>bạn yêu thích.</em></h1>
          <p>Khám phá một không gian mua sắm trực quan với trải nghiệm tìm kiếm, lọc sản phẩm và giỏ hàng demo hoạt động thật.</p>
          <div className="hero-actions">
            <a className="hero-primary" href="#products">Khám phá sản phẩm <span aria-hidden="true">↗</span></a>
            <a className="hero-secondary" href="#categories">Xem danh mục <span aria-hidden="true">→</span></a>
          </div>
          <div className="hero-caption"><span>✳</span> Được tạo để thử năng lực ứng dụng web · Không mở bán</div>
        </div>
        <div className="hero-visual" role="img" aria-label="Hình khối trang trí màu cam và kem, không phải hình sản phẩm">
          <div className="hero-disc disc-back"/><div className="hero-disc disc-front"/>
          <div className="hero-tile"><span>curated<br/>for you.</span><span className="tile-asterisk">✳</span></div>
          <span className="floating-badge badge-left">Fresh finds <strong>✦</strong></span>
          <span className="floating-badge badge-right">every day ↗</span>
        </div>
      </section>
      <div className="site-container benefits-bar">
        <span><b>01</b> Tìm kiếm trực tiếp</span>
        <span><b>02</b> Lọc theo danh mục</span>
        <span><b>03</b> Giỏ hàng tương tác</span>
        <span><b>04</b> Hoàn toàn local</span>
      </div>
      <section id="categories" className="site-container categories-section">
        <div className="section-heading"><div><div className="section-eyebrow">KHÁM PHÁ</div>
          <h2>Danh mục nổi bật<span className="coral-dot">.</span></h2></div><p>Chọn một danh mục để xem sản phẩm phù hợp.</p></div>
        <div className="category-grid">
          {CATEGORIES.filter(c=>c.id!=='all').map(c=><button key={c.id}
            className={'category-tile '+(category===c.id?'is-active':'')} onClick={()=>selectCategory(c.id)}
            aria-pressed={category===c.id}>
            <span className="category-icon">{c.icon}</span><strong>{c.name}</strong><span className="category-chevron">↗</span>
          </button>)}
        </div>
      </section>
      <section className="site-container promo-section" aria-label="Thông tin bản demo">
        <div className="promo-copy"><span>THỬ NGHIỆM TƯƠNG TÁC</span><h2>Không chỉ là<br/><em>một landing page.</em></h2>
        <p>Thử tìm sản phẩm, thay đổi bộ lọc và thêm vào giỏ. Mọi thao tác chỉ diễn ra trong trình duyệt của bạn.</p></div>
        <span className="promo-art" aria-hidden="true">✳</span><a href="#products">Bắt đầu thử ↗</a>
      </section>
      <section id="products" className="site-container products-section">
        <div className="section-heading"><div><div className="section-eyebrow">GIAN HÀNG DEMO</div>
          <h2>Khám phá hôm nay<span className="coral-dot">.</span></h2></div><p>Giá và sản phẩm là dữ liệu thử nghiệm, không phải chào bán.</p></div>
        <div className="filterbar">
          <div className="filter-chips" role="group" aria-label="Lọc sản phẩm theo danh mục">
            {CATEGORIES.map(c=><button key={c.id} className={'filter-chip '+(category===c.id?'active':'')}
              onClick={()=>setCategory(c.id)} aria-pressed={category===c.id}>{c.name}</button>)}
          </div>
          <label className="sort-select">Sắp xếp
            <select value={sort} onChange={e=>setSort(e.target.value)}>
              <option value="featured">Gợi ý</option>
              <option value="price-asc">Giá thấp → cao</option>
              <option value="price-desc">Giá cao → thấp</option>
            </select></label>
        </div>
        <div className="results-label" aria-live="polite">{visible.length} sản phẩm demo
          {(search||category!=='all')&&<button onClick={reset}>Xóa bộ lọc ×</button>}
        </div>
        {visible.length>0?<div className="product-grid">
          {visible.map(product=><ProductCard key={product.id} product={product} onInspect={setSelected} onAdd={add}/>)}
        </div>:<div className="empty-state"><div>⌕</div><h3>Chưa tìm thấy sản phẩm</h3>
          <p>Thử từ khóa khác hoặc xóa bộ lọc hiện tại.</p><button className="hero-primary" onClick={reset}>Xem tất cả sản phẩm</button></div>}
      </section>
      <section className="site-container footer-banner"><div><span>HÀNH TRÌNH TIẾP THEO</span>
        <h2>Từ ý tưởng đến <em>ứng dụng thực tế.</em></h2>
        <p>NovaMart là bài kiểm tra tính tương tác cho AgentForge V4. Không kết nối tài khoản, thanh toán hay giao vận.</p>
      </div><span className="footer-banner-art" aria-hidden="true">↗</span></section>
    </main>
    <footer className="site-footer"><div className="site-container footer-inner"><div>
      <strong>nova<span>mart</span><i>.</i></strong><p>Marketplace demo · AgentForge V4</p></div>
      <p>Dữ liệu giả lập · Không có đơn hàng thật · Hoạt động offline sau khi build</p></div></footer>
    {toast&&<div className="toast" role="status">{toast}</div>}
    {selected&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setSelected(null);}}>
      <section className="detail-dialog" role="dialog" aria-modal="true" aria-label={'Chi tiết '+selected.name}>
        <button className="close-button" onClick={()=>setSelected(null)} aria-label="Đóng chi tiết">×</button>
        <div className="detail-image">{display(selected)}</div>
        <div className="detail-copy"><span className="section-eyebrow">SẢN PHẨM MINH HỌA</span>
          <h2>{selected.name}</h2><p className="detail-category">{categoryName(selected.category)}</p>
          <strong className="detail-price">{currency(selected.price)}</strong>
          <p>{selected.description}</p><p className="demo-disclaimer">Giá demo để kiểm thử UI, không phải báo giá hoặc ưu đãi thật.</p>
          <button className="hero-primary" onClick={()=>{add(selected.id);setSelected(null);}}>
            + Thêm vào giỏ demo</button></div>
      </section></div>}
    {cartOpen&&<div className="overlay drawer-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setCartOpen(false);}}>
      <aside className="cart-drawer" role="dialog" aria-modal="true" aria-label="Giỏ hàng demo">
        <div className="drawer-header"><div><span className="section-eyebrow">NOVA CART</span><h2>Giỏ hàng của bạn</h2>
          <p>{totals.items} sản phẩm demo</p></div>
          <button className="close-button" onClick={()=>setCartOpen(false)} aria-label="Đóng giỏ hàng">×</button></div>
        <div className="drawer-content">
          {cartProducts.length===0?<div className="cart-empty"><span>◇</span><h3>Giỏ hàng đang trống</h3>
            <p>Thêm vài sản phẩm để kiểm thử tính năng mua sắm.</p>
            <button className="hero-primary" onClick={()=>setCartOpen(false)}>Khám phá sản phẩm</button></div>:
            cartProducts.map(product=><div className="cart-line" key={product.id}>
              <span className={'cart-art tone-'+product.tone} aria-hidden="true">{product.icon}</span>
              <div className="cart-line-content"><strong>{product.name}</strong><span>{currency(product.price)}</span>
                <div className="quantity-controls"><button onClick={()=>setCart(prev=>changeCart(prev,product.id,-1,KNOWN))}
                  aria-label={'Giảm số lượng '+product.name}>−</button><b>{cart[product.id]}</b>
                  <button onClick={()=>setCart(prev=>changeCart(prev,product.id,1,KNOWN))}
                    aria-label={'Tăng số lượng '+product.name}>+</button>
                  <button className="remove-item" onClick={()=>setCart(prev=>removeFromCart(prev,product.id))}>Xóa</button>
                </div></div>
            </div>)}
        </div>
        <div className="drawer-bottom"><div className="cart-total"><span>Tạm tính (demo)</span><strong>{currency(totals.total)}</strong></div>
          <button disabled className="checkout-disabled">Thanh toán chưa được hỗ trợ</button>
          <p>Không có thanh toán, tài khoản hay đơn hàng thật.</p></div>
      </aside></div>}
  </div>;
}
