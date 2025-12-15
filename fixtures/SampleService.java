package com.example.fixtures;

import java.util.List;

/**
 * Simple fixture used by tests for tree-sitter parsing.
 */
public class SampleService {

    private final DatabaseConnection db;

    /**
     * Constructs a new SampleService.
     *
     * @param db the database connection
     */
    public SampleService(DatabaseConnection db) {
        this.db = db;
        validateConnection(db);
    }

    /**
     * Creates a user and persists it.
     *
     * @param username username
     * @param email email
     * @return id
     */
    public String createUser(String username, String email) {
        validateEmail(email);
        String id = generateUserId();
        saveToDatabase(id, username);
        return id;
    }

    /** Validates the email format. */
    private void validateEmail(String email) {
        if (!email.contains("@")) {
            throw new IllegalArgumentException("Invalid email");
        }
    }

    private String generateUserId() {
        return "U_" + System.currentTimeMillis();
    }

    private void saveToDatabase(String id, String username) {
        db.execute("INSERT INTO users VALUES (?, ?)", id, username);
    }

    private void validateConnection(DatabaseConnection db) {
        if (db == null) {
            throw new IllegalArgumentException("db cannot be null");
        }
    }

    public List<String> listUsernames() {
        // generic return type to exercise `generic_type` signature extraction
        return db.queryUsernames();
    }

    public interface Hasher {
        String hash(String input);
    }

    public static class DatabaseConnection {
        public void execute(String sql, String a, String b) {
        }

        public List<String> queryUsernames() {
            return java.util.Collections.emptyList();
        }
    }
}
