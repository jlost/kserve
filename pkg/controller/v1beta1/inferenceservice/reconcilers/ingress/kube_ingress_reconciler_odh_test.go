/*
Copyright 2025 The KServe Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

// ODH-specific tests for the RawIngressReconciler.
// Delete this entire file when backporting to upstream.

package ingress

import (
	"strconv"
	"testing"

	. "github.com/onsi/gomega"
	routev1 "github.com/openshift/api/route/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	"github.com/kserve/kserve/pkg/apis/serving/v1beta1"
	"github.com/kserve/kserve/pkg/constants"
)

func testSchemeODH() *runtime.Scheme {
	s := testScheme()
	_ = routev1.AddToScheme(s)
	return s
}

// ---------------------------------------------------------------------------
// TestCreateAddress_Auth -- auth-enabled address tests
// ---------------------------------------------------------------------------

func TestCreateAddress_Auth(t *testing.T) {
	const (
		isvcName  = "test-isvc"
		namespace = "default"
	)

	tests := []struct {
		name       string
		headless   bool
		wantScheme string
		wantHost   string
	}{
		{
			name:       "auth enabled, ClusterIP service",
			headless:   false,
			wantScheme: "https",
			wantHost:   predictorHost(isvcName, namespace) + ":" + strconv.Itoa(constants.OauthProxyPort),
		},
		{
			name:       "auth enabled, headless service -- auth wins over headless port",
			headless:   true,
			wantScheme: "https",
			wantHost:   predictorHost(isvcName, namespace) + ":" + strconv.Itoa(constants.OauthProxyPort),
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			g := NewGomegaWithT(t)
			s := testScheme()

			svcName := constants.PredictorServiceName(isvcName)
			svc := makeService(svcName, namespace, tc.headless)
			cl := fake.NewClientBuilder().WithScheme(s).WithObjects(svc).Build()

			isvc := &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{Name: isvcName, Namespace: namespace},
				Spec:       v1beta1.InferenceServiceSpec{Predictor: v1beta1.PredictorSpec{}},
			}

			addr, err := createAddress(t.Context(), cl, isvc, true)
			g.Expect(err).ToNot(HaveOccurred())
			g.Expect(addr).ToNot(BeNil())
			g.Expect(addr.URL.Scheme).To(Equal(tc.wantScheme))
			g.Expect(addr.URL.Host).To(Equal(tc.wantHost))
		})
	}
}

// ---------------------------------------------------------------------------
// TestCreateRawURLODH -- unit tests for createRawURLODH
// ---------------------------------------------------------------------------

func TestCreateRawURLODH(t *testing.T) {
	const (
		isvcName  = "test-isvc"
		namespace = "default"
	)

	tests := []struct {
		name        string
		authEnabled bool
		wantScheme  string
		wantHost    string
	}{
		{
			name:        "no auth -- plain HTTP, no port",
			authEnabled: false,
			wantScheme:  "http",
			wantHost:    predictorHost(isvcName, namespace),
		},
		{
			name:        "auth enabled -- HTTPS with OAuth proxy port",
			authEnabled: true,
			wantScheme:  "https",
			wantHost:    predictorHost(isvcName, namespace) + ":" + strconv.Itoa(constants.OauthProxyPort),
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			g := NewGomegaWithT(t)
			s := testScheme()
			cl := fake.NewClientBuilder().WithScheme(s).Build()

			isvc := &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{Name: isvcName, Namespace: namespace},
				Spec:       v1beta1.InferenceServiceSpec{Predictor: v1beta1.PredictorSpec{}},
			}

			url, err := createRawURLODH(t.Context(), cl, isvc, tc.authEnabled)
			g.Expect(err).ToNot(HaveOccurred())
			g.Expect(url.Scheme).To(Equal(tc.wantScheme))
			g.Expect(url.Host).To(Equal(tc.wantHost))
		})
	}
}

func TestCreateRawURLODH_Transformer(t *testing.T) {
	g := NewGomegaWithT(t)
	const (
		isvcName  = "test-isvc"
		namespace = "default"
	)
	s := testScheme()
	cl := fake.NewClientBuilder().WithScheme(s).Build()

	isvc := &v1beta1.InferenceService{
		ObjectMeta: metav1.ObjectMeta{Name: isvcName, Namespace: namespace},
		Spec: v1beta1.InferenceServiceSpec{
			Predictor:   v1beta1.PredictorSpec{},
			Transformer: &v1beta1.TransformerSpec{},
		},
	}

	url, err := createRawURLODH(t.Context(), cl, isvc, false)
	g.Expect(err).ToNot(HaveOccurred())
	g.Expect(url.Host).To(Equal(transformerHost(isvcName, namespace)))
}

func TestCreateRawURLODH_RouteMode(t *testing.T) {
	g := NewGomegaWithT(t)
	const (
		isvcName  = "test-isvc"
		namespace = "default"
		routeHost = "test-isvc-default.apps.example.com"
	)
	s := testSchemeODH()

	isvcUID := types.UID("test-uid-1234")

	route := &routev1.Route{
		ObjectMeta: metav1.ObjectMeta{
			Name:      isvcName,
			Namespace: namespace,
			OwnerReferences: []metav1.OwnerReference{
				{UID: isvcUID},
			},
		},
		Spec: routev1.RouteSpec{
			Host: routeHost,
			TLS:  &routev1.TLSConfig{Termination: routev1.TLSTerminationEdge},
		},
		Status: routev1.RouteStatus{
			Ingress: []routev1.RouteIngress{
				{
					Conditions: []routev1.RouteIngressCondition{
						{Type: "Admitted", Status: "True"},
					},
				},
			},
		},
	}

	cl := fake.NewClientBuilder().WithScheme(s).WithObjects(route).Build()

	isvc := &v1beta1.InferenceService{
		ObjectMeta: metav1.ObjectMeta{
			Name:      isvcName,
			Namespace: namespace,
			UID:       isvcUID,
			Labels: map[string]string{
				constants.NetworkVisibility: constants.ODHRouteEnabled,
			},
		},
		Spec: v1beta1.InferenceServiceSpec{Predictor: v1beta1.PredictorSpec{}},
	}

	url, err := createRawURLODH(t.Context(), cl, isvc, false)
	g.Expect(err).ToNot(HaveOccurred())
	g.Expect(url.Scheme).To(Equal("https"))
	g.Expect(url.Host).To(Equal(routeHost))
}

// ---------------------------------------------------------------------------
// TestRawIngressReconciler_URLAndAddress_Auth -- auth-enabled reconciler tests
//
// Mirrors the matrix from TestRawIngressReconciler_URLAndAddress but with
// authEnabled=true. Pairs varying urlScheme must produce identical results.
// ---------------------------------------------------------------------------

func TestRawIngressReconciler_URLAndAddress_Auth(t *testing.T) {
	const (
		isvcName  = "test-isvc"
		namespace = "default"
	)

	pHost := predictorHost(isvcName, namespace)
	authHost := pHost + ":" + strconv.Itoa(constants.OauthProxyPort)

	tests := []struct {
		name        string
		headless    bool
		urlScheme   string
		wantURL     string
		wantAddress string
	}{
		{
			name:        "auth, ClusterIP, urlScheme=http",
			headless:    false,
			urlScheme:   "http",
			wantURL:     "https://" + authHost,
			wantAddress: "https://" + authHost,
		},
		{
			name:        "auth, ClusterIP, urlScheme=https -- urlScheme has no effect",
			headless:    false,
			urlScheme:   "https",
			wantURL:     "https://" + authHost,
			wantAddress: "https://" + authHost,
		},
		{
			name:        "auth, headless, urlScheme=http -- auth wins over headless port",
			headless:    true,
			urlScheme:   "http",
			wantURL:     "https://" + authHost,
			wantAddress: "https://" + authHost,
		},
		{
			name:        "auth, headless, urlScheme=https -- auth wins, urlScheme no effect",
			headless:    true,
			urlScheme:   "https",
			wantURL:     "https://" + authHost,
			wantAddress: "https://" + authHost,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			g := NewGomegaWithT(t)
			s := testScheme()

			svcName := constants.PredictorServiceName(isvcName)
			svc := makeService(svcName, namespace, tc.headless)
			cl := fake.NewClientBuilder().WithScheme(s).WithObjects(svc).Build()

			isvc := &v1beta1.InferenceService{
				ObjectMeta: metav1.ObjectMeta{
					Name:      isvcName,
					Namespace: namespace,
					Annotations: map[string]string{
						constants.ODHKserveRawAuth: "true",
					},
				},
				Spec:   v1beta1.InferenceServiceSpec{Predictor: v1beta1.PredictorSpec{}},
				Status: v1beta1.InferenceServiceStatus{},
			}

			ingressConfig := &v1beta1.IngressConfig{
				DisableIngressCreation: true,
				UrlScheme:              tc.urlScheme,
			}
			isvcConfig := &v1beta1.InferenceServicesConfig{
				ServiceAnnotationDisallowedList: []string{},
				ServiceLabelDisallowedList:      []string{},
			}

			reconciler, err := NewRawIngressReconciler(cl, s, ingressConfig, isvcConfig)
			g.Expect(err).ToNot(HaveOccurred())

			result, err := reconciler.Reconcile(t.Context(), isvc)
			g.Expect(err).ToNot(HaveOccurred())
			g.Expect(result).To(Equal(ctrl.Result{}))

			g.Expect(isvc.Status.URL).ToNot(BeNil(), "Status.URL should be set")
			g.Expect(isvc.Status.URL.String()).To(Equal(tc.wantURL))

			g.Expect(isvc.Status.Address).ToNot(BeNil(), "Status.Address should be set")
			g.Expect(isvc.Status.Address.URL.String()).To(Equal(tc.wantAddress))

			cond := isvc.Status.GetCondition(v1beta1.IngressReady)
			g.Expect(cond).ToNot(BeNil())
			g.Expect(cond.Status).To(Equal(corev1.ConditionTrue))
		})
	}
}
