package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// Test SMS Gateway health check
func TestCheckSMSGatewayHealth(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		wantErr    bool
	}{
		{
			name:       "healthy gateway",
			statusCode: http.StatusOK,
			wantErr:    false,
		},
		{
			name:       "unhealthy gateway",
			statusCode: http.StatusServiceUnavailable,
			wantErr:    true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create mock SMS Gateway
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/health" {
					t.Errorf("Expected path /health, got %s", r.URL.Path)
				}
				w.WriteHeader(tt.statusCode)
			}))
			defer ts.Close()

			// Test health check
			err := CheckSMSGatewayHealth(ts.URL)
			if (err != nil) != tt.wantErr {
				t.Errorf("CheckSMSGatewayHealth() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

// Test SMS Gateway client webhook operations
func TestSMSGatewayClient(t *testing.T) {
	// Create mock SMS Gateway
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Check basic auth
		username, password, ok := r.BasicAuth()
		if !ok || username != "test" || password != "pass" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		switch r.Method {
		case "GET":
			if r.URL.Path == "/webhooks" {
				webhooks := []Webhook{
					{ID: "1", URL: "http://test.com", Event: "sms:received"},
					{ID: "2", URL: "http://test.com", Event: "sms:sent"},
				}
				json.NewEncoder(w).Encode(webhooks)
			}
		case "DELETE":
			if r.URL.Path == "/webhooks/1" {
				w.WriteHeader(http.StatusNoContent)
			}
		case "POST":
			if r.URL.Path == "/webhooks" {
				w.WriteHeader(http.StatusCreated)
			}
		}
	}))
	defer ts.Close()

	client := NewSMSGatewayClient(ts.URL, "test", "pass")

	// Test GetWebhooks
	webhooks, err := client.GetWebhooks()
	if err != nil {
		t.Fatalf("GetWebhooks failed: %v", err)
	}
	if len(webhooks) != 2 {
		t.Errorf("Expected 2 webhooks, got %d", len(webhooks))
	}

	// Test DeleteWebhook
	if err := client.DeleteWebhook("1"); err != nil {
		t.Errorf("DeleteWebhook failed: %v", err)
	}

	// Test RegisterWebhook
	if err := client.RegisterWebhook("sms:received", "http://localhost:8000/webhook/sms:received"); err != nil {
		t.Errorf("RegisterWebhook failed: %v", err)
	}
}

// Test SetupWebhooks
func TestSetupWebhooks(t *testing.T) {
	// Create mock SMS Gateway
	deleteCount := 0
	registerCount := 0
	
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case "GET":
			if r.URL.Path == "/webhooks" {
				webhooks := []Webhook{
					{ID: "old1", URL: "http://old.com", Event: "sms:received"},
				}
				json.NewEncoder(w).Encode(webhooks)
			}
		case "DELETE":
			deleteCount++
			w.WriteHeader(http.StatusNoContent)
		case "POST":
			registerCount++
			w.WriteHeader(http.StatusCreated)
		}
	}))
	defer ts.Close()

	client := NewSMSGatewayClient(ts.URL, "test", "pass")
	
	// Test SetupWebhooks
	err := SetupWebhooks(client, "8000")
	if err != nil {
		t.Fatalf("SetupWebhooks failed: %v", err)
	}

	// Should have deleted 1 old webhook
	if deleteCount != 1 {
		t.Errorf("Expected 1 delete, got %d", deleteCount)
	}

	// Should have registered 4 new webhooks
	if registerCount != 4 {
		t.Errorf("Expected 4 registrations, got %d", registerCount)
	}
}