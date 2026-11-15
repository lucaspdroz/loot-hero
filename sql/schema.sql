CREATE DATABASE IF NOT EXISTS games_deals CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE games_deals;

CREATE TABLE IF NOT EXISTS stores (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      slug VARCHAR(80) NOT NULL, name VARCHAR(160) NOT NULL, base_url VARCHAR(500) NULL,
      source_type ENUM('store','editorial') NOT NULL DEFAULT 'store', enabled TINYINT(1) NOT NULL DEFAULT 1,
      created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
      updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
      PRIMARY KEY (id), UNIQUE KEY uq_stores_slug (slug)
    ) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS games (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, canonical_key VARCHAR(255) NOT NULL,
      title VARCHAR(500) NOT NULL, normalized_title VARCHAR(500) NOT NULL, steam_app_id BIGINT UNSIGNED NULL,
      cover_image_url TEXT NULL, created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
      updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
      PRIMARY KEY (id), UNIQUE KEY uq_games_canonical_key (canonical_key),
      KEY idx_games_steam_app_id (steam_app_id), KEY idx_games_normalized_title (normalized_title(191))
    ) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS deals (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

    store_id BIGINT UNSIGNED NOT NULL,
    game_id BIGINT UNSIGNED NULL,
    platform_id BIGINT UNSIGNED NULL,

    external_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,

    banner_img TEXT NULL,
    product_url TEXT NOT NULL,
    affiliate_url TEXT NULL,

    current_price DECIMAL(12,2) NOT NULL,
    original_price DECIMAL(12,2) NULL,
    currency CHAR(3) NOT NULL DEFAULT 'BRL',
    discount_percent DECIMAL(6,2) NULL,

    region VARCHAR(16) NOT NULL DEFAULT 'BR',
    available TINYINT(1) NOT NULL DEFAULT 1,

    last_check_at DATETIME(6) NOT NULL,
    first_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (id),

    UNIQUE KEY uq_deals_store_external (store_id, external_id),

    KEY idx_deals_game (game_id),
    KEY idx_deals_platform (platform_id),
    KEY idx_deals_price (currency, current_price),
    KEY idx_deals_discount (discount_percent),
    KEY idx_deals_available (available, last_check_at),

    CONSTRAINT fk_deals_store
        FOREIGN KEY (store_id) REFERENCES stores(id),

    CONSTRAINT fk_deals_game
        FOREIGN KEY (game_id) REFERENCES games(id)
        ON DELETE SET NULL

) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS price_history (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, deal_id BIGINT UNSIGNED NOT NULL,
      price DECIMAL(12,2) NOT NULL, original_price DECIMAL(12,2) NULL, currency CHAR(3) NOT NULL,
      discount_percent DECIMAL(6,2) NULL, collected_at DATETIME(6) NOT NULL,
      PRIMARY KEY (id), KEY idx_price_history_deal_date (deal_id, collected_at),
      CONSTRAINT fk_price_history_deal FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS editorial_items (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, store_id BIGINT UNSIGNED NOT NULL,
      external_id VARCHAR(500) NOT NULL, title VARCHAR(500) NOT NULL, article_url TEXT NOT NULL,
      summary TEXT NULL, published_at DATETIME(6) NULL, collected_at DATETIME(6) NOT NULL,
      PRIMARY KEY (id), UNIQUE KEY uq_editorial_store_external (store_id, external_id(191)),
      KEY idx_editorial_published (published_at),
      CONSTRAINT fk_editorial_store FOREIGN KEY (store_id) REFERENCES stores(id)
    ) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS crawler_runs (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, store_id BIGINT UNSIGNED NOT NULL,
      status ENUM('running','success','partial','failed') NOT NULL,
      items_seen INT UNSIGNED NOT NULL DEFAULT 0, items_saved INT UNSIGNED NOT NULL DEFAULT 0,
      duration_ms INT UNSIGNED NULL, error_message TEXT NULL, started_at DATETIME(6) NOT NULL,
      finished_at DATETIME(6) NULL, PRIMARY KEY (id), KEY idx_crawler_runs_store_started (store_id, started_at),
      CONSTRAINT fk_crawler_runs_store FOREIGN KEY (store_id) REFERENCES stores(id)
    ) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS platforms (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, slug VARCHAR(50) NOT NULL, name VARCHAR(100) NOT NULL,
      PRIMARY KEY (id), UNIQUE KEY uq_platforms_slug (slug)
    ) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS free_games (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, store_id BIGINT UNSIGNED NOT NULL, game_id BIGINT UNSIGNED NULL,
      external_id VARCHAR(255) NOT NULL, title VARCHAR(500) NOT NULL, banner_img TEXT NULL,
      platform_id BIGINT UNSIGNED NULL, starts_at DATETIME NOT NULL, ends_at DATETIME NOT NULL,
      is_on_banner TINYINT(1) NOT NULL DEFAULT 0,
      status ENUM('upcoming','active','expired') NOT NULL DEFAULT 'upcoming', product_url TEXT NULL,
      first_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
      last_checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
      created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
      updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
      PRIMARY KEY (id), UNIQUE KEY uq_free_games_offer (store_id, external_id, starts_at),
      KEY idx_free_games_status (status), KEY idx_free_games_dates (starts_at, ends_at), KEY idx_free_games_game (game_id),
      CONSTRAINT fk_free_games_store FOREIGN KEY (store_id) REFERENCES stores(id),
      CONSTRAINT fk_free_games_game FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE SET NULL,
      CONSTRAINT fk_free_games_platform FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE SET NULL
    ) ENGINE=InnoDB;

INSERT INTO stores (slug,name,base_url,source_type) VALUES
('steam','Steam','https://store.steampowered.com','store'),
('epic-games','Epic Games Store','https://store.epicgames.com','store'),
('kinguin','Kinguin','https://www.kinguin.net','store'),
('gameplayscassi','Gameplayscassi','https://gameplayscassi.com.br/category/promocoes','editorial'),
('greenmangaming','Green Man Gaming','https://www.greenmangaming.com','store'),
('instantgaming','Instant Gaming','https://www.instant-gaming.com','store')
ON DUPLICATE KEY UPDATE name=VALUES(name), base_url=VALUES(base_url), source_type=VALUES(source_type);

INSERT INTO platforms (slug,name) VALUES ('pc','PC') ON DUPLICATE KEY UPDATE name=VALUES(name);