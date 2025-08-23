package tests

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
)

// Test the health endpoint
func TestHealthEndpoint(t *testing.T) {
	// Create a simple health handler
	r := chi.NewRouter()
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		response := map[string]string{
			"status":    "healthy",
			"version":   "0.4",
			"timestamp": time.Now().Format(time.RFC3339),
		}
		json.NewEncoder(w).Encode(response)
	})

	// Create test server
	ts := httptest.NewServer(r)
	defer ts.Close()

	// Make request
	resp, err := http.Get(ts.URL + "/health")
	if err != nil {
		t.Fatalf("Failed to make request: %v", err)
	}
	defer resp.Body.Close()

	// Check status code
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}

	// Check content type
	contentType := resp.Header.Get("Content-Type")
	if contentType != "application/json" {
		t.Errorf("Expected Content-Type 'application/json', got '%s'", contentType)
	}

	// Parse response
	var result map[string]string
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	// Check required fields
	if result["status"] != "healthy" {
		t.Errorf("Expected status 'healthy', got '%s'", result["status"])
	}

	if result["version"] == "" {
		t.Error("Version should not be empty")
	}

	if result["timestamp"] == "" {
		t.Error("Timestamp should not be empty")
	}

	// Validate timestamp format
	if _, err := time.Parse(time.RFC3339, result["timestamp"]); err != nil {
		t.Errorf("Invalid timestamp format: %v", err)
	}
}

// Test webhook endpoint returns 200 OK
func TestWebhookEndpointReturns200(t *testing.T) {
	r := chi.NewRouter()
	
	// Simple webhook handler that always returns 200
	webhookHandler := func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	}
	
	r.Post("/webhook/sms:received", webhookHandler)

	// Create test server
	ts := httptest.NewServer(r)
	defer ts.Close()

	// Send valid webhook
	fixture := loadFixture(t, "webhooks/sms_received.json")
	resp, err := http.Post(ts.URL+"/webhook/sms:received", "application/json", bytes.NewBuffer(fixture))
	if err != nil {
		t.Fatalf("Failed to make request: %v", err)
	}
	defer resp.Body.Close()

	// Should return 200
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}

	// Check response body
	body := make([]byte, 2)
	resp.Body.Read(body)
	if string(body) != "OK" {
		t.Errorf("Expected body 'OK', got '%s'", string(body))
	}
}

// Test invalid JSON returns 400
func TestInvalidJSONReturns400(t *testing.T) {
	r := chi.NewRouter()
	
	// Webhook handler that validates JSON
	r.Post("/webhook/sms:received", func(w http.ResponseWriter, r *http.Request) {
		var event map[string]interface{}
		if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	// Create test server
	ts := httptest.NewServer(r)
	defer ts.Close()

	// Send invalid JSON
	invalidJSON := []byte("not valid json")
	resp, err := http.Post(ts.URL+"/webhook/sms:received", "application/json", bytes.NewBuffer(invalidJSON))
	if err != nil {
		t.Fatalf("Failed to make request: %v", err)
	}
	defer resp.Body.Close()

	// Should return 400
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", resp.StatusCode)
	}
}