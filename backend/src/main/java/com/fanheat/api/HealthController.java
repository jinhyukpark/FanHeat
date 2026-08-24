package com.fanheat.api;

import java.time.Instant;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/health")
public class HealthController {
    @GetMapping
    public Map<String, Object> health() {
        return Map.of(
                "status", "ok",
                "service", "fanheat-backend",
                "framework", "Spring Boot",
                "timestamp", Instant.now().toString()
        );
    }

    @RestController
    @Profile("supabase")
    @RequestMapping("/api/health/database")
    static class DatabaseHealthController {
        private final JdbcTemplate jdbcTemplate;

        DatabaseHealthController(JdbcTemplate jdbcTemplate) {
            this.jdbcTemplate = jdbcTemplate;
        }

        @GetMapping
        Map<String, Object> databaseHealth() {
            Integer result = jdbcTemplate.queryForObject("select 1", Integer.class);
            return Map.of("status", result != null && result == 1 ? "ok" : "error", "database", "supabase-postgres");
        }
    }
}
