// 骨架屏加载组件

export function GenealogySkeletonLoader() {
  return (
    <div className="genealogy-skeleton">
      {[...Array(8)].map((_, i) => (
        <div 
          key={i} 
          className="skeleton-node" 
          style={{ marginLeft: ((i % 3) * 20) + 'px' }}
        >
          <div className="skeleton-avatar shimmer"></div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div className="skeleton-text shimmer" style={{ width: '70%' }}></div>
            <div className="skeleton-text shimmer short" style={{ width: '40%' }}></div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function MapSkeletonLoader() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '1rem' }}>
      {[...Array(5)].map((_, i) => (
        <div key={i} className="skeleton-node">
          <div className="skeleton-text shimmer long"></div>
        </div>
      ))}
    </div>
  );
}

export function SpeciesSkeletonLoader() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem' }}>
      <div className="skeleton-text shimmer" style={{ height: '24px', width: '80%' }}></div>
      <div className="skeleton-text shimmer" style={{ height: '16px', width: '60%' }}></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginTop: '1rem' }}>
        {[...Array(4)].map((_, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div className="skeleton-text shimmer" style={{ height: '14px', width: '50%' }}></div>
            <div className="skeleton-text shimmer" style={{ height: '18px', width: '70%' }}></div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LoadingSpinner({ size = 20 }: { size?: number }) {
  return (
    <div 
      className="spinner" 
      style={{ width: size, height: size, borderWidth: Math.max(2, size / 8) }}
    ></div>
  );
}

