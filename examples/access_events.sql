-- Example MySQL schema (access-control events)
CREATE TABLE `access_events` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `tenant_id` int(11) NOT NULL,
  `badge_id` varchar(64) NOT NULL,
  `door_id` int(11) DEFAULT NULL,
  `event_type` enum('GRANTED','DENIED','FORCED') NOT NULL COMMENT 'Result of the access attempt',
  `is_visitor` tinyint(1) NOT NULL DEFAULT '0',
  `amount` decimal(10,2) DEFAULT NULL,
  `payload` json DEFAULT NULL,
  `created_at` datetime(3) NOT NULL,
  PRIMARY KEY (`tenant_id`,`id`),
  KEY `idx_badge` (`badge_id`),
  CONSTRAINT `fk_door` FOREIGN KEY (`door_id`) REFERENCES `doors` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS doors (
  id int unsigned NOT NULL PRIMARY KEY,
  name varchar(100) NOT NULL,
  installed_on date
);
