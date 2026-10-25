import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, Package, MapPin, CalendarCheck, FileText, ArrowRight } from 'lucide-react';
import { apiFetch } from '../../lib/api';

interface SearchItem {
  id: string;
  title: string;
  subtitle?: string;
  category?: string;
  href: string;
}

interface SearchData {
  query: string;
  total: number;
  results: {
    products?: SearchItem[];
    locations?: SearchItem[];
    plans?: SearchItem[];
    pages?: SearchItem[];
  };
}

export function TopBarSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchData, setSearchData] = useState<SearchData | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isMobileExpanded, setIsMobileExpanded] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounce query
  useEffect(() => {
    if (!isOpen) return;

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await apiFetch<SearchData>(
          `/api/v1/search?q=${encodeURIComponent(query.trim())}`
        );
        setSearchData(data);
        setSelectedIndex(-1);
      } catch (err) {
        // quiet error fallback
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query, isOpen]);

  // Global keyboard shortcut: Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setIsMobileExpanded(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Flattened list of results for keyboard arrow navigation
  const flatItems: SearchItem[] = React.useMemo(() => {
    if (!searchData?.results) return [];
    const { pages = [], products = [], locations = [], plans = [] } = searchData.results;
    return [...pages, ...products, ...locations, ...plans];
  }, [searchData]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
      setIsMobileExpanded(false);
      inputRef.current?.blur();
      return;
    }

    if (!isOpen || flatItems.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % flatItems.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + flatItems.length) % flatItems.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0 && selectedIndex < flatItems.length) {
        selectItem(flatItems[selectedIndex]);
      } else if (flatItems.length > 0) {
        selectItem(flatItems[0]);
      }
    }
  };

  const selectItem = (item: SearchItem) => {
    navigate(item.href);
    setIsOpen(false);
    setIsMobileExpanded(false);
    setQuery('');
  };

  const getCategoryIcon = (category?: string) => {
    switch (category?.toLowerCase()) {
      case 'product':
        return <Package className="w-4 h-4 text-brand shrink-0" strokeWidth={1.5} />;
      case 'location':
        return <MapPin className="w-4 h-4 text-turmeric shrink-0" strokeWidth={1.5} />;
      case 'plan':
        return <CalendarCheck className="w-4 h-4 text-madder shrink-0" strokeWidth={1.5} />;
      default:
        return <FileText className="w-4 h-4 text-ink-3 shrink-0" strokeWidth={1.5} />;
    }
  };

  return (
    <div ref={containerRef} className="relative flex-1 max-w-[460px] mx-4">
      {/* Search Input Bar */}
      <div
        className={`flex items-center gap-2 px-3 py-2 bg-paper/80 hover:bg-paper focus-within:bg-surface border border-line focus-within:border-brand rounded-control transition-all shadow-inner-quiet ${
          isMobileExpanded ? 'fixed inset-x-2 top-3 z-50 max-w-none bg-surface shadow-lg' : ''
        }`}
      >
        <Search className="w-4 h-4 text-ink-3 shrink-0" strokeWidth={1.5} />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!isOpen) setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search products, locations, or plans…"
          className="w-full bg-transparent text-body text-ink placeholder:text-ink-3 focus:outline-none text-[13px]"
        />
        {query ? (
          <button
            type="button"
            onClick={() => {
              setQuery('');
              inputRef.current?.focus();
            }}
            className="p-0.5 text-ink-3 hover:text-ink rounded-full"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        ) : (
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-semibold text-ink-3 bg-surface border border-line rounded-chip select-none">
            <span>⌘K</span>
          </kbd>
        )}
      </div>

      {/* Dropdown Results Popover */}
      {isOpen && (
        <div
          className={`absolute left-0 right-0 top-full mt-1.5 bg-surface border border-line rounded-control shadow-overlay overflow-hidden z-50 max-h-[420px] overflow-y-auto ${
            isMobileExpanded ? 'fixed inset-x-2 top-16 max-h-[70vh]' : ''
          }`}
        >
          {loading && (
            <div className="py-4 text-center text-meta text-ink-3">Searching catalog…</div>
          )}

          {!loading && searchData && searchData.total === 0 && (
            <div className="py-6 text-center text-meta text-ink-3">
              No matching records found for "{query}".
            </div>
          )}

          {!loading && searchData && searchData.total > 0 && (
            <div className="py-2 flex flex-col divide-y divide-line/40">
              {/* Pages */}
              {searchData.results.pages && searchData.results.pages.length > 0 && (
                <div className="py-1">
                  <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                    Pages
                  </div>
                  {searchData.results.pages.map((item) => {
                    const idx = flatItems.indexOf(item);
                    const isSelected = idx === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectItem(item)}
                        className={`w-full px-3 py-2 flex items-center justify-between text-left text-[13px] hover:bg-brand-wash/60 transition-colors ${
                          isSelected ? 'bg-brand-wash text-brand font-medium' : 'text-ink'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {getCategoryIcon(item.category)}
                          <div className="truncate">
                            <div className="font-medium truncate">{item.title}</div>
                            {item.subtitle && (
                              <div className="text-[11px] text-ink-3 truncate">{item.subtitle}</div>
                            )}
                          </div>
                        </div>
                        <ArrowRight className="w-3.5 h-3.5 text-ink-3 shrink-0" strokeWidth={1.5} />
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Products */}
              {searchData.results.products && searchData.results.products.length > 0 && (
                <div className="py-1">
                  <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                    Products
                  </div>
                  {searchData.results.products.map((item) => {
                    const idx = flatItems.indexOf(item);
                    const isSelected = idx === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectItem(item)}
                        className={`w-full px-3 py-2 flex items-center justify-between text-left text-[13px] hover:bg-brand-wash/60 transition-colors ${
                          isSelected ? 'bg-brand-wash text-brand font-medium' : 'text-ink'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {getCategoryIcon(item.category)}
                          <div className="truncate">
                            <div className="font-medium truncate">{item.title}</div>
                            {item.subtitle && (
                              <div className="text-[11px] text-ink-3 truncate">{item.subtitle}</div>
                            )}
                          </div>
                        </div>
                        <span className="text-[11px] font-mono text-ink-3 shrink-0">{item.id}</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Locations */}
              {searchData.results.locations && searchData.results.locations.length > 0 && (
                <div className="py-1">
                  <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                    Locations
                  </div>
                  {searchData.results.locations.map((item) => {
                    const idx = flatItems.indexOf(item);
                    const isSelected = idx === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectItem(item)}
                        className={`w-full px-3 py-2 flex items-center justify-between text-left text-[13px] hover:bg-brand-wash/60 transition-colors ${
                          isSelected ? 'bg-brand-wash text-brand font-medium' : 'text-ink'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {getCategoryIcon(item.category)}
                          <div className="truncate">
                            <div className="font-medium truncate">{item.title}</div>
                            {item.subtitle && (
                              <div className="text-[11px] text-ink-3 truncate">{item.subtitle}</div>
                            )}
                          </div>
                        </div>
                        <span className="text-[11px] font-mono text-ink-3 shrink-0">{item.id}</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Plans */}
              {searchData.results.plans && searchData.results.plans.length > 0 && (
                <div className="py-1">
                  <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                    Plan Runs
                  </div>
                  {searchData.results.plans.map((item) => {
                    const idx = flatItems.indexOf(item);
                    const isSelected = idx === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectItem(item)}
                        className={`w-full px-3 py-2 flex items-center justify-between text-left text-[13px] hover:bg-brand-wash/60 transition-colors ${
                          isSelected ? 'bg-brand-wash text-brand font-medium' : 'text-ink'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {getCategoryIcon(item.category)}
                          <div className="truncate">
                            <div className="font-medium truncate">{item.title}</div>
                            {item.subtitle && (
                              <div className="text-[11px] text-ink-3 truncate">{item.subtitle}</div>
                            )}
                          </div>
                        </div>
                        <span className="text-[11px] font-mono text-ink-3 shrink-0">{item.id}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
