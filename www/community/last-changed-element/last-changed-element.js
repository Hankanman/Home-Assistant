class LastChangedElement extends HTMLElement {

    second = 1000;
    minute = this.second * 60;
    hour = this.minute * 60;
    day = this.hour * 24;
    month = this.day * 30;
    year = this.day * 365;

    timeAgo = (last_changed_millis) => {
        const diff = new Date().getTime() - last_changed_millis;
        switch (true) {
            case diff < this.minute:
                const seconds = Math.round(diff / 1000);
                return seconds + 's';
            case diff < this.hour:
                return Math.round(diff / this.minute) + 'm';
            case diff < this.day:
                return Math.round(diff / this.hour) + 'h';
            case diff < this.month:
                return Math.round(diff / this.day) + 'd';
            case diff < this.year:
                return Math.round(diff / this.month) + 'M';
            case diff > this.year:
                return Math.round(diff / this.year) + 'y';
            default:
                return "";
        }
    };

    set hass(hass) {
        if (!this.content) {
            this.content = document.createElement('text-element');
            this.appendChild(this.content);
        }

        const entityId = this.config.entity;
        const state = hass.states[entityId];
        let stateStr = '-';

        try {
            if (state) {
                const last_changed_millis = (new Date(state.last_changed)).getTime();
                stateStr = this.timeAgo(last_changed_millis);
                this.setTimer(last_changed_millis);
            }
        } catch (ex) {

        }

        this.setContent(stateStr);
    }

    setConfig(config) {
        if (!config.entity) {
            throw new Error('You need to define an entity');
        }
        this.config = config;
    }

    getCardSize() {
        return 1;
    }

    setContent(str) {
        this.content.innerHTML = str;
    }

    setTimer(last_changed_millis) {
        if (this.timer) {
            clearTimeout(this.timer);
        }

        const diff = new Date().getTime() - last_changed_millis;
        let nextInterval;
        if (diff < this.minute) {
            nextInterval = this.second;
        } else if (diff < this.hour) {
            nextInterval = this.minute;
        }

        if (nextInterval) {
            this.timer = setTimeout(() => {
                this.setContent(this.timeAgo(last_changed_millis));
                this.setTimer(last_changed_millis);
            }, nextInterval);
        }
    }
}

customElements.define('last-changed-element', LastChangedElement);
