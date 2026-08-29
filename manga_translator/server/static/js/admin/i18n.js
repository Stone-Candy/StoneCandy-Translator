// 管理端国际化支持
class AdminI18n {
    constructor() {
        this.currentLocale = localStorage.getItem('admin_locale') || this.detectLocale();
        this.translations = {};
        this.fallbackLocale = 'zh_CN';
    }
    
    detectLocale() {
        const browserLang = navigator.language.replace('-', '_');
        if (browserLang.startsWith('zh_CN') || browserLang.startsWith('zh-CN')) return 'zh_CN';
        if (browserLang.startsWith('zh')) return 'zh_TW';
        if (browserLang.startsWith('en')) return 'en_US';
        if (browserLang.startsWith('ja')) return 'ja_JP';
        if (browserLang.startsWith('ko')) return 'ko_KR';
        return 'zh_CN';
    }
    
    async init() {
        await this.loadTranslations(this.currentLocale);
        if (this.currentLocale !== this.fallbackLocale) {
            await this.loadTranslations(this.fallbackLocale);
        }
    }
    
    async loadTranslations(locale) {
        try {
            const resp = await fetch(`/i18n/${locale}`);
            if (resp.ok) {
                this.translations[locale] = await resp.json();
            }
        } catch (e) {
            console.error(`Failed to load translations for ${locale}:`, e);
            this.translations[locale] = {};
        }
    }
    
    t(key, defaultText = '') {
        let text = this.translations[this.currentLocale]?.[key];
        if (!text && this.currentLocale !== this.fallbackLocale) {
            text = this.translations[this.fallbackLocale]?.[key];
        }
        return text || defaultText || key;
    }
    
    async setLocale(locale) {
        this.currentLocale = locale;
        localStorage.setItem('admin_locale', locale);
        if (!this.translations[locale]) {
            await this.loadTranslations(locale);
        }
    }
    
    getAvailableLocales() {
        return [
            { code: 'zh_CN', name: '简体中文' },
            { code: 'zh_TW', name: '繁體中文' },
            { code: 'en_US', name: 'English' },
            { code: 'ja_JP', name: '日本語' },
            { code: 'ko_KR', name: '한국어' }
        ];
    }
}

window.AdminI18n = AdminI18n;
window.i18n = new AdminI18n();
