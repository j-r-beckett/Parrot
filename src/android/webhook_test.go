package main

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// Test fixture loading
func loadFixture(t *testing.T, path string) []byte {
	fullPath := filepath.Join("tests/testdata", path)
	data, err := os.ReadFile(fullPath)
	if err != nil {
		t.Fatalf("Failed to load fixture %s: %v", path, err)
	}
	return data
}

// Test webhook handlers with real fixtures
func TestWebhookHandlers(t *testing.T) {
	tests := []struct {
		name        string
		event       string
		fixturePath string
		wantStatus  int
	}{
		{
			name:        "valid sms:received",
			event:       "sms:received",
			fixturePath: "webhooks/sms_received.json",
			wantStatus:  http.StatusOK,
		},
		{
			name:        "valid sms:sent",
			event:       "sms:sent",
			fixturePath: "webhooks/sms_sent.json",
			wantStatus:  http.StatusOK,
		},
		{
			name:        "valid sms:delivered",
			event:       "sms:delivered",
			fixturePath: "webhooks/sms_delivered.json",
			wantStatus:  http.StatusOK,
		},
		{
			name:        "valid sms:failed",
			event:       "sms:failed",
			fixturePath: "webhooks/sms_failed.json",
			wantStatus:  http.StatusOK,
		},
		{
			name:        "malformed webhook",
			event:       "sms:received",
			fixturePath: "webhooks/malformed.json",
			wantStatus:  http.StatusBadRequest,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Load fixture
			fixture := loadFixture(t, tt.fixturePath)

			// Create the actual webhook handler with a dummy client manager
			cm := NewClientManager()
			handler := CreateWebhookHandler(tt.event, cm)

			// Create test request
			req := httptest.NewRequest("POST", "/webhook/"+tt.event, bytes.NewBuffer(fixture))
			req.Header.Set("Content-Type", "application/json")

			// Record response
			rr := httptest.NewRecorder()
			handler.ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.wantStatus {
				t.Errorf("handler returned wrong status code: got %v want %v", status, tt.wantStatus)
			}

			// Check OK response for successful requests
			if tt.wantStatus == http.StatusOK {
				body := rr.Body.String()
				if body != "OK" {
					t.Errorf("expected body 'OK', got '%s'", body)
				}
			}
		})
	}
}

// Test webhook parsing with invalid JSON
func TestWebhookHandlerInvalidJSON(t *testing.T) {
	cm := NewClientManager()
	handler := CreateWebhookHandler("sms:received", cm)
	
	// Send invalid JSON
	req := httptest.NewRequest("POST", "/webhook/sms:received", bytes.NewBufferString("not json"))
	rr := httptest.NewRecorder()
	
	handler.ServeHTTP(rr, req)
	
	if status := rr.Code; status != http.StatusBadRequest {
		t.Errorf("expected status 400, got %v", status)
	}
}