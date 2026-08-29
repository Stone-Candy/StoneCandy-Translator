// 国际化模块 - 与Qt UI共享翻译文件
class I18n {
    constructor() {
        this.locale = localStorage.getItem('locale') || 'zh_CN';
        this.translations = {};
        this.loaded = false;
    }
    
    async load() {
        try {
            // 直接从Qt UI的locales目录加载，方便统一维护
            const resp = await fetch(`/locales/${this.locale}.json`);
            if (resp.ok) {
                this.translations = await resp.json();
                this.loaded = true;
            } else {
                console.warn(`Failed to load locale ${this.locale}, using fallback`);
                this.translations = {};
            }
        } catch (e) {
            console.error('Failed to load translations:', e);
            this.translations = {};
        }
    }
    
    t(key, fallback = null, params = {}) {
        let text = this.translations[key] || fallback || key;
        // 替换参数 {param}
        for (const [k, v] of Object.entries(params)) {
            text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
        }
        return text;
    }
    
    setLocale(locale) {
        this.locale = locale;
        localStorage.setItem('locale', locale);
        return this.load();
    }
    
    getLocale() {
        return this.locale;
    }
}

// 全局实例
window.i18n = new I18n();
